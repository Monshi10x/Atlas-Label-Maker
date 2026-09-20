(() => {
  const MM_TO_PT = 72 / 25.4;
  const PT_TO_MM = 25.4 / 72;

  const state = {
    templates: [],
    selectedTemplateId: null,
    uploads: [],
    settings: {},
    lastOutputFolder: "",
    editor: null,
    editorSelectedSlot: -1,
    confirmAction: null,
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    templateSelect: $("templateSelect"),
    acceptedSize: $("acceptedSize"),
    slotCount: $("slotCount"),
    pageSize: $("pageSize"),
    detectionNote: $("detectionNote"),
    editTemplateButton: $("editTemplateButton"),
    labelFileInput: $("labelFileInput"),
    labelDropZone: $("labelDropZone"),
    labelList: $("labelList"),
    dropHint: $("dropHint"),
    generateCombined: $("generateCombined"),
    generateIndividual: $("generateIndividual"),
    combinedName: $("combinedName"),
    outputFolder: $("outputFolder"),
    generateButton: $("generateButton"),
    resultPanel: $("resultPanel"),
    resultTitle: $("resultTitle"),
    resultText: $("resultText"),
    openFolderButton: $("openFolderButton"),
    managerList: $("managerList"),
    busyOverlay: $("busyOverlay"),
    busyTitle: $("busyTitle"),
    busyText: $("busyText"),
    appStatus: $("appStatus"),
    editorName: $("editorName"),
    editorWidth: $("editorWidth"),
    editorHeight: $("editorHeight"),
    editorPositionX: $("editorPositionX"),
    editorPositionY: $("editorPositionY"),
    editorMeta: $("editorMeta"),
    pageMap: $("pageMap"),
    editorTitle: $("editorTitle"),
    rotateSlotButton: $("rotateSlotButton"),
    deleteSlotButton: $("deleteSlotButton"),
    openMasterLink: $("openMasterLink"),
  };

  let activeRowId=null, previewUrl=null, previewGeneration=0, customFont=false;
  let toolTemplates=[], toolFolder="";
  const previewReady=import('/static/label-preview.mjs').then(m=>new m.LabelPreview($("designViewer"),$("designCanvas")));
  const jsonPost=body=>({method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const activeRow=()=>state.uploads.find(row=>row.rowId===activeRowId);
  const chosenTool=()=>toolTemplates.find(t=>t.id===$("toolTemplateSelect").value);
  function rowPayload(row){return {source_token:row.source_token,tool_template_id:row.tool_template_id,template_folder:row.template_folder,title:row.title,specification:row.specification,use_custom_font:!!row.use_custom_font,editable:row.editable};}
  function syncCombinedName(){
    const row=activeRow();
    el.combinedName.value=row ? ('Tool Label - '+row.title.trim()+' '+row.specification.trim()).trim().replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,180) : 'Tool Label';
    $("combinedNameHint").textContent=row ? `Automatically follows label row ${state.uploads.indexOf(row)+1}. Select another row to change the name.` : 'Automatically follows the selected label row.';
  }
  function clearDesignPreview(){previewGeneration++;previewReady.then(p=>p.clear()).catch(()=>{});if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;$("designNotice").textContent='';}
  function selectRow(id){activeRowId=id;syncCombinedName();clearDesignPreview();el.labelList.querySelectorAll('tr[data-row]').forEach(tr=>{tr.classList.toggle('selected',tr.dataset.row===id);tr.querySelector('input[type=radio]').checked=tr.dataset.row===id;});}
  function addRow(){
    const t=chosenTool();if(!t)return toast('Choose a tool-label template.','error');
    const row={rowId:crypto.randomUUID(),tool_template_id:t.id,template_folder:toolFolder,filename:t.id,title:t.title,specification:t.specification,editable:true,use_custom_font:false,width_pt:t.width_pt,height_pt:t.height_pt,width_mm:55,height_mm:15};
    state.uploads.push(row);activeRowId=row.rowId;clearDesignPreview();renderUploads();
  }
  async function loadToolTemplates(data=null){
    data=data || await api('/api/tool-templates');const previous=$("toolTemplateSelect").value;
    toolTemplates=data.templates;toolFolder=data.folder;$("toolTemplateFolder").value=toolFolder;$("toolTemplateSelect").replaceChildren();
    toolTemplates.forEach(t=>{const o=document.createElement('option');o.value=t.id;o.textContent=t.name;$("toolTemplateSelect").append(o);});
    if(toolTemplates.some(t=>t.id===previous))$("toolTemplateSelect").value=previous;
    $("addLabelRow").disabled=!toolTemplates.length;$("toolTemplateErrors").textContent=data.errors.join('\n');
  }
  $("addLabelRow").addEventListener('click',addRow);
  $("toolTemplateSelect").addEventListener('change',()=>{
    const row=activeRow(),t=chosenTool();if(!t)return;
    if(row){const old=row.source_token;Object.assign(row,{source_token:null,tool_template_id:t.id,template_folder:toolFolder,filename:t.id,title:t.title,specification:t.specification,editable:true,use_custom_font:false,width_pt:t.width_pt,height_pt:t.height_pt,width_mm:55,height_mm:15});if(old)api(`/api/labels/${old}`,{method:'DELETE'}).catch(()=>{});clearDesignPreview();renderUploads();}
    else addRow();
    previewSelected(false);
  });
  async function changeFolder(browse){showBusy('LOADING TEMPLATES');try{const data=await api('/api/tool-templates/folder',jsonPost(browse?{}:{folder:$("toolTemplateFolder").value}));if(!data.cancelled)await loadToolTemplates(data);}catch(e){toast(e.message,'error');}finally{hideBusy();}}
  $("chooseToolFolder").addEventListener('click',()=>changeFolder(true));
  $("refreshToolTemplates").addEventListener('click',()=>changeFolder(false));
  $("openToolFolder").addEventListener('click',()=>api('/api/open-folder',jsonPost({path:toolFolder})).catch(e=>toast(e.message,'error')));
  $("designFontUpload").addEventListener('click',()=>$("designFontFile").click());
  $("designFontFile").addEventListener('change',async()=>{const file=$("designFontFile").files[0];if(!file)return;showBusy('SAVING FONT');try{if(file.size>10*1024*1024)throw Error('Font must be under 10 MB.');await api('/api/designer/font',{method:'POST',body:file});customFont=true;renderUploads();clearDesignPreview();toast('Font saved. Choose Uploaded in the row font selector to use it.');}catch(e){toast(e.message,'error');}finally{hideBusy();$("designFontFile").value='';}});
  async function previewSelected(download){
    const row=activeRow();if(!row)return toast('Add or select a label row.','error');
    clearDesignPreview();const generation=previewGeneration;const payload=rowPayload(row);showBusy('CREATING LABEL');
    try{const response=await api('/api/designer/preview',jsonPost(payload));const blob=await response.blob();if(generation!==previewGeneration)return;previewUrl=URL.createObjectURL(blob);
      if(download){const a=document.createElement('a');a.href=previewUrl;a.download=el.combinedName.value+'.pdf';a.click();}
      await (await previewReady).show(blob);
      if(generation===previewGeneration)$("designNotice").textContent=`Label ${state.uploads.indexOf(row)+1} · ${fmtDimensions(row.width_mm,row.height_mm)} · fitted to viewer · print at 100%.`;
    }catch(e){toast(e.message,'error',8000);}finally{hideBusy();}
  }
  $("designPreview").addEventListener('click',()=>previewSelected(false));
  $("designDownload").addEventListener('click',()=>previewSelected(true));

  function selectedTemplate() {
    return state.templates.find((t) => t.id === state.selectedTemplateId) || null;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        if (contentType.includes("json")) {
          const payload = await response.json();
          message = payload.error || message;
        } else {
          message = (await response.text()) || message;
        }
      } catch (_) {}
      throw new Error(message);
    }
    if (contentType.includes("json")) return response.json();
    return response;
  }

  function showBusy(title, text) {
    el.busyTitle.textContent = title;
    el.busyText.textContent = text || "Please wait…";
    el.busyOverlay.classList.remove("hidden");
    el.appStatus.textContent = "WORKING";
  }

  function hideBusy() {
    el.busyOverlay.classList.add("hidden");
    el.appStatus.textContent = "READY";
  }

  function toast(message, type = "success", timeout = 4200) {
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.textContent = message;
    $("toastStack").appendChild(node);
    window.setTimeout(() => node.remove(), timeout);
  }

  function openModal(id) { $(id).classList.remove("hidden"); }
  function closeModal(id) { $(id).classList.add("hidden"); }

  function fmtMm(value) {
    const n = Number(value);
    return Math.abs(n - Math.round(n)) < 0.005 ? `${Math.round(n)} mm` : `${n.toFixed(2)} mm`;
  }

  function fmtDimensions(w, h) {
    return `${fmtMm(w).replace(" mm", "")} × ${fmtMm(h)}`;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function loadStatus() {
    const payload = await api("/api/status");
    state.settings = payload.settings || {};
    state.lastOutputFolder = state.settings.last_output_folder || "";
    el.outputFolder.value = state.last_output_folder || "";
    syncCombinedName();
  }

  async function loadTemplates(preferredId = null) {
    const payload = await api("/api/templates");
    state.templates = payload.templates || [];
    const existing = preferredId || state.selectedTemplateId;
    state.selectedTemplateId = state.templates.some((t) => t.id === existing)
      ? existing
      : (state.templates[0]?.id || null);
    renderTemplateSelect();
    renderManagerList();
    updateTemplateSummary();
  }

  function renderTemplateSelect() {
    el.templateSelect.innerHTML = "";
    if (!state.templates.length) {
      const option = document.createElement("option");
      option.textContent = "No saved templates";
      option.value = "";
      el.templateSelect.appendChild(option);
      el.templateSelect.disabled = true;
      el.editTemplateButton.disabled = true;
      return;
    }
    el.templateSelect.disabled = false;
    for (const template of state.templates) {
      const option = document.createElement("option");
      option.value = template.id;
      option.textContent = template.name;
      option.selected = template.id === state.selectedTemplateId;
      el.templateSelect.appendChild(option);
    }
    el.editTemplateButton.disabled = !state.selectedTemplateId;
  }

  function updateTemplateSummary() {
    const template = selectedTemplate();
    if (!template) {
      el.acceptedSize.textContent = "-";
      el.slotCount.textContent = "-";
      el.pageSize.textContent = "-";
      el.detectionNote.textContent = "Add or import a template to begin.";
      el.dropHint.textContent = "Choose a template before adding replacement labels.";
      updateUploadStatuses();
      return;
    }
    el.acceptedSize.textContent = fmtDimensions(template.accepted_width_mm, template.accepted_height_mm);
    el.slotCount.textContent = String(template.slot_count);
    const pageW = template.page_width_pt * PT_TO_MM;
    const pageH = template.page_height_pt * PT_TO_MM;
    el.pageSize.textContent = template.is_a5 ? "A5" : fmtDimensions(pageW, pageH);
    el.detectionNote.textContent = `Placement map: ${template.detection_method}. All ${template.slot_count} positions use the same ${fmtDimensions(template.accepted_width_mm, template.accepted_height_mm)} PDF size.`;
    el.dropHint.textContent = `Accepts ${fmtDimensions(template.accepted_width_mm, template.accepted_height_mm)} single-page PDFs.`;
    updateUploadStatuses();
  }

  function sizeMatches(upload, template) {
    if (!template) return false;
    return Math.abs(upload.width_pt - template.accepted_width_pt) <= 0.75
      && Math.abs(upload.height_pt - template.accepted_height_pt) <= 0.75;
  }

  function updateUploadStatuses() {
    renderUploads();
  }

  function renderUploads(){
    if(!state.uploads.some(r=>r.rowId===activeRowId))activeRowId=state.uploads[0]?.rowId || null;
    syncCombinedName();$("designPreview").disabled=!activeRow();$("designDownload").disabled=!activeRow();
    el.labelList.innerHTML='';if(!state.uploads.length){el.labelList.innerHTML='<p class="note-line">Add a label or upload PDFs to begin.</p>';return;}
    const table=document.createElement('table');table.className='label-table';
    table.innerHTML='<thead><tr><th>Select</th><th>Source PDF</th><th>Tool name</th><th>Specification</th><th>Font</th><th></th></tr></thead>';
    const body=document.createElement('tbody');table.append(body);
    state.uploads.forEach((row,i)=>{
      const tr=document.createElement('tr');tr.dataset.row=row.rowId;tr.classList.toggle('selected',row.rowId===activeRowId);
      const status=sizeMatches(row,selectedTemplate()) ? (row.editable?'Editable':'PDF kept unchanged') : 'SIZE MISMATCH';
      tr.innerHTML=`<td><input type="radio" name="selectedLabel" aria-label="Select label ${i+1}" ${row.rowId===activeRowId?'checked':''}></td><td class="source-cell">${escapeHtml(row.filename)}<small>${escapeHtml(status)}</small></td><td><input type="text" data-key="title" aria-label="Tool name ${i+1}" maxlength="100" value="${escapeHtml(row.title)}" ${row.editable?'':'readonly'}></td><td><input type="text" data-key="specification" aria-label="Specification ${i+1}" maxlength="100" value="${escapeHtml(row.specification)}" ${row.editable?'':'readonly'}></td><td><select aria-label="Font ${i+1}" ${row.editable?'':'disabled'}><option value="bundled">Poppins</option><option value="custom" ${customFont?'':'disabled'}>Uploaded</option></select></td><td><button class="file-remove" aria-label="Remove label ${i+1}">×</button></td>`;
      tr.querySelector('input[type=radio]').addEventListener('change',()=>selectRow(row.rowId));
      tr.querySelectorAll('input[data-key]').forEach(input=>{input.addEventListener('focus',()=>{if(activeRowId!==row.rowId)selectRow(row.rowId);});input.addEventListener('input',()=>{row[input.dataset.key]=input.value;syncCombinedName();clearDesignPreview();});});
      const select=tr.querySelector('select');select.value=row.use_custom_font?'custom':'bundled';select.addEventListener('change',()=>{row.use_custom_font=select.value==='custom';selectRow(row.rowId);});
      tr.querySelector('button').addEventListener('click',async()=>{state.uploads=state.uploads.filter(r=>r.rowId!==row.rowId);clearDesignPreview();renderUploads();if(row.source_token)await api(`/api/labels/${row.source_token}`,{method:'DELETE'}).catch(()=>{});});
      body.append(tr);
    });el.labelList.append(table);
  }

  async function uploadLabels(files) {
    if (!files?.length) return;
    if (!selectedTemplate()) {
      toast("Choose a template before adding replacement labels.", "error");
      return;
    }
    showBusy("ADDING LABELS", `Uploading ${files.length} PDF${files.length === 1 ? "" : "s"}…`);
    try {
      for (let i = 0; i < files.length; i += 1) {
        const file = files[i];
        el.busyText.textContent = `${i + 1} of ${files.length}: ${file.name}`;
        const payload = await api("/api/labels/upload", {
          method: "POST",
          headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/pdf" },
          body: file,
        });
        const row={...payload.upload,source_token:payload.upload.token,rowId:crypto.randomUUID(),use_custom_font:false};
        state.uploads.push(row);activeRowId=row.rowId;
      }
      renderUploads();
      toast(`${files.length} label PDF${files.length === 1 ? "" : "s"} added.`);
    } catch (error) {
      toast(error.message, "error", 7000);
    } finally {
      renderUploads();clearDesignPreview();hideBusy();
      el.labelFileInput.value = "";
    }
  }

  function renderManagerList() {
    if (!el.managerList) return;
    el.managerList.innerHTML = "";
    if (!state.templates.length) {
      el.managerList.innerHTML = `<div class="note-line">No templates are saved. Add an A5 PDF template to create the first layout.</div>`;
      return;
    }
    for (const template of state.templates) {
      const item = document.createElement("div");
      item.className = "manager-item";
      item.innerHTML = `
        <div><strong>${escapeHtml(template.name)}</strong><small>${fmtDimensions(template.accepted_width_mm, template.accepted_height_mm)} · ${template.slot_count} positions · ${escapeHtml(template.detection_method)}</small></div>
        <div class="manager-actions">
          <button class="button outline" data-action="select" data-id="${template.id}">SELECT</button>
          <button class="button outline" data-action="edit" data-id="${template.id}">EDIT</button>
          <button class="button outline" data-action="duplicate" data-id="${template.id}">DUPLICATE</button>
          <button class="button danger" data-action="delete" data-id="${template.id}">DELETE</button>
        </div>`;
      el.managerList.appendChild(item);
    }
    el.managerList.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.id;
        const action = button.dataset.action;
        if (action === "select") {
          state.selectedTemplateId = id;
          renderTemplateSelect();
          updateTemplateSummary();
          closeModal("templateManagerModal");
        } else if (action === "edit") {
          openTemplateEditor(id);
        } else if (action === "duplicate") {
          showBusy("DUPLICATING TEMPLATE", "Creating a permanent copy…");
          try {
            const payload = await api(`/api/templates/${id}/duplicate`, { method: "POST", body: new Uint8Array([1]) });
            await loadTemplates(payload.template.id);
            toast("Template duplicated.");
          } catch (error) { toast(error.message, "error"); }
          finally { hideBusy(); }
        } else if (action === "delete") {
          const template = state.templates.find((t) => t.id === id);
          confirmDialog(
            "DELETE TEMPLATE?",
            `“${template?.name || "This template"}” and its saved master PDF will be removed from this computer.`,
            async () => {
              showBusy("DELETING TEMPLATE", "Updating the permanent library…");
              try {
                await api(`/api/templates/${id}`, { method: "DELETE" });
                await loadTemplates();
                toast("Template deleted.");
              } catch (error) { toast(error.message, "error"); }
              finally { hideBusy(); }
            }
          );
        }
      });
    });
  }

  async function addTemplate(file) {
    if (!file) return;
    const proposedName = file.name.replace(/\.pdf$/i, "");
    showBusy("ANALYSING TEMPLATE", "Detecting linked PDF positions and accepted label size…");
    try {
      const payload = await api("/api/templates/upload", {
        method: "POST",
        headers: {
          "X-Filename": encodeURIComponent(file.name),
          "X-Template-Name": encodeURIComponent(proposedName),
          "Content-Type": "application/pdf",
        },
        body: file,
      });
      await loadTemplates(payload.template.id);
      toast(`Template added with ${payload.template.slot_count} detected positions.`);
      openTemplateEditor(payload.template.id);
    } catch (error) {
      toast(error.message, "error", 8000);
    } finally {
      hideBusy();
      $("newTemplateInput").value = "";
    }
  }

  async function addBlankTemplate() {
    showBusy("CREATING TEMPLATE", "Creating a blank A5 placement template…");
    try {
      const payload = await api("/api/templates/blank", { method: "POST", body: new Uint8Array([1]) });
      await loadTemplates(payload.template.id);
      toast("Blank A5 template created. Add and position labels in the editor.");
      openTemplateEditor(payload.template.id);
    } catch (error) {
      toast(error.message, "error", 8000);
    } finally {
      hideBusy();
    }
  }

  function deepCopy(value) { return JSON.parse(JSON.stringify(value)); }

  function openTemplateEditor(id) {
    const template = state.templates.find((t) => t.id === id);
    if (!template) return;
    state.editor = deepCopy(template);
    state.editorSelectedSlot = -1;
    el.editorName.value = template.name;
    el.editorWidth.value = Number(template.accepted_width_mm).toFixed(2);
    el.editorHeight.value = Number(template.accepted_height_mm).toFixed(2);
    el.editorTitle.textContent = template.name;
    el.openMasterLink.href = `/api/templates/${template.id}/master.pdf`;
    renderEditor();
    openModal("templateEditorModal");
  }

  function editorDimensionsPt() {
    return {
      width: Math.max(1, Number(el.editorWidth.value || 0)) * MM_TO_PT,
      height: Math.max(1, Number(el.editorHeight.value || 0)) * MM_TO_PT,
    };
  }

  function transformBBox(width, height, matrix) {
    const [a, b, c, d, e, f] = matrix.map(Number);
    const points = [[0,0], [width,0], [0,height], [width,height]].map(([x,y]) => [a*x + c*y + e, b*x + d*y + f]);
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[1]);
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  }

  function matrixForBBox(x, y, rotation, labelW, labelH) {
    const rot = ((rotation % 360) + 360) % 360;
    if (rot === 90) return [0, 1, -1, 0, x + labelH, y];
    if (rot === 180) return [-1, 0, 0, -1, x + labelW, y + labelH];
    if (rot === 270) return [0, -1, 1, 0, x, y + labelW];
    return [1, 0, 0, 1, x, y];
  }

  function renderEditor() {
    if (!state.editor) return;
    const template = state.editor;
    const dims = editorDimensionsPt();
    el.editorMeta.innerHTML = `Page: ${(template.page_width_pt * PT_TO_MM).toFixed(2)} × ${(template.page_height_pt * PT_TO_MM).toFixed(2)} mm<br>Positions: ${template.slots.length}<br>Detected from: ${escapeHtml(template.detection_method)}`;
    el.pageMap.innerHTML = "";
    template.slots.forEach((slot, index) => {
      const bbox = transformBBox(dims.width, dims.height, slot.matrix);
      const box = document.createElement("div");
      box.className = `slot-box${index === state.editorSelectedSlot ? " selected" : ""}`;
      box.dataset.index = String(index);
      box.style.left = `${bbox.x / template.page_width_pt * 100}%`;
      box.style.top = `${(template.page_height_pt - bbox.y - bbox.h) / template.page_height_pt * 100}%`;
      box.style.width = `${bbox.w / template.page_width_pt * 100}%`;
      box.style.height = `${bbox.h / template.page_height_pt * 100}%`;
      box.textContent = String(index + 1);
      box.title = `Position ${index + 1} · ${slot.rotation || 0}°`;
      box.addEventListener("pointerdown", startSlotDrag);
      el.pageMap.appendChild(box);
    });
    const hasSelection = state.editorSelectedSlot >= 0 && state.editorSelectedSlot < template.slots.length;
    el.rotateSlotButton.disabled = !hasSelection;
    el.deleteSlotButton.disabled = !hasSelection;
    syncEditorPositionFields();
  }

  function syncEditorPositionFields() {
    const slot = state.editor?.slots[state.editorSelectedSlot];
    const hasSelection = Boolean(slot);
    el.editorPositionX.disabled = !hasSelection;
    el.editorPositionY.disabled = !hasSelection;
    if (!hasSelection) {
      el.editorPositionX.value = "";
      el.editorPositionY.value = "";
      return;
    }
    const dims = editorDimensionsPt();
    const bbox = transformBBox(dims.width, dims.height, slot.matrix);
    el.editorPositionX.value = (bbox.x * PT_TO_MM).toFixed(2);
    el.editorPositionY.value = (bbox.y * PT_TO_MM).toFixed(2);
  }

  function updateEditorPosition() {
    const slot = state.editor?.slots[state.editorSelectedSlot];
    if (!slot || !state.editor) return;
    const xMm = Number(el.editorPositionX.value);
    const yMm = Number(el.editorPositionY.value);
    if (!Number.isFinite(xMm) || !Number.isFinite(yMm)) return;
    const dims = editorDimensionsPt();
    const bbox = transformBBox(dims.width, dims.height, slot.matrix);
    const x = Math.min(Math.max(0, xMm * MM_TO_PT), Math.max(0, state.editor.page_width_pt - bbox.w));
    const y = Math.min(Math.max(0, yMm * MM_TO_PT), Math.max(0, state.editor.page_height_pt - bbox.h));
    slot.matrix = matrixForBBox(x, y, slot.rotation || 0, dims.width, dims.height);
    renderEditor();
  }

  function selectEditorSlot(index) {
    state.editorSelectedSlot = index;
    renderEditor();
  }

  function startSlotDrag(event) {
    if (!state.editor) return;
    event.preventDefault();
    const index = Number(event.currentTarget.dataset.index);
    selectEditorSlot(index);
    const slot = state.editor.slots[index];
    const dims = editorDimensionsPt();
    const startBBox = transformBBox(dims.width, dims.height, slot.matrix);
    const startX = event.clientX;
    const startY = event.clientY;
    const mapRect = el.pageMap.getBoundingClientRect();
    const move = (moveEvent) => {
      const dxPt = (moveEvent.clientX - startX) / mapRect.width * state.editor.page_width_pt;
      const dyPt = -(moveEvent.clientY - startY) / mapRect.height * state.editor.page_height_pt;
      let x = startBBox.x + dxPt;
      let y = startBBox.y + dyPt;
      x = Math.min(Math.max(0, x), Math.max(0, state.editor.page_width_pt - startBBox.w));
      y = Math.min(Math.max(0, y), Math.max(0, state.editor.page_height_pt - startBBox.h));
      slot.matrix = matrixForBBox(x, y, slot.rotation || 0, dims.width, dims.height);
      renderEditor();
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
  }

  function updateEditorDimensions() {
    if (!state.editor) return;
    const oldW = state.editor.accepted_width_pt;
    const oldH = state.editor.accepted_height_pt;
    const next = editorDimensionsPt();
    state.editor.slots.forEach((slot) => {
      const bbox = transformBBox(oldW, oldH, slot.matrix);
      slot.matrix = matrixForBBox(bbox.x, bbox.y, slot.rotation || 0, next.width, next.height);
    });
    state.editor.accepted_width_pt = next.width;
    state.editor.accepted_height_pt = next.height;
    state.editor.accepted_width_mm = next.width * PT_TO_MM;
    state.editor.accepted_height_mm = next.height * PT_TO_MM;
    renderEditor();
  }

  async function saveTemplateEditor() {
    if (!state.editor) return;
    const widthMm = Number(el.editorWidth.value);
    const heightMm = Number(el.editorHeight.value);
    if (!Number.isFinite(widthMm) || !Number.isFinite(heightMm) || widthMm <= 0 || heightMm <= 0) {
      toast("Enter valid label dimensions.", "error");
      return;
    }
    showBusy("SAVING TEMPLATE", "Updating the permanent template library…");
    try {
      const payload = await api(`/api/templates/${state.editor.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: el.editorName.value,
          accepted_width_mm: widthMm,
          accepted_height_mm: heightMm,
          slots: state.editor.slots.map((slot) => ({ id: slot.id, matrix: slot.matrix })),
        }),
      });
      await loadTemplates(payload.template.id);
      closeModal("templateEditorModal");
      toast("Template changes saved permanently.");
    } catch (error) {
      toast(error.message, "error", 7000);
    } finally { hideBusy(); }
  }

  function confirmDialog(title, text, action) {
    $("confirmTitle").textContent = title;
    $("confirmText").textContent = text;
    state.confirmAction = action;
    openModal("confirmModal");
  }

  async function exportLibrary() {
    showBusy("EXPORTING LIBRARY", "Packaging all templates into one portable file…");
    try {
      const response = await api("/api/templates/export", { method: "POST", body: new Uint8Array([1]) });
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match?.[1] || "Atlas-Label-Templates.atlaslabels";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast("Template library exported.");
    } catch (error) { toast(error.message, "error"); }
    finally { hideBusy(); }
  }

  async function importLibrary(file) {
    if (!file) return;
    showBusy("IMPORTING LIBRARY", "Restoring templates from the portable library file…");
    try {
      const payload = await api("/api/templates/import", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      await loadTemplates();
      toast(`${payload.imported} template${payload.imported === 1 ? "" : "s"} restored. The previous library was backed up automatically.`);
    } catch (error) { toast(error.message, "error", 7000); }
    finally { hideBusy(); $("importLibraryInput").value = ""; }
  }

  async function replaceMaster(file) {
    if (!file || !state.editor) return;
    showBusy("REPLACING MASTER", "Re-detecting every placement position…");
    try {
      const payload = await api(`/api/templates/${state.editor.id}/replace-master`, {
        method: "POST",
        headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/pdf" },
        body: file,
      });
      await loadTemplates(payload.template.id);
      openTemplateEditor(payload.template.id);
      toast(`Master replaced. ${payload.template.slot_count} positions detected.`);
    } catch (error) { toast(error.message, "error", 8000); }
    finally { hideBusy(); $("replaceMasterInput").value = ""; }
  }

  async function chooseFolder() {
    showBusy("CHOOSING FOLDER", "Opening the Windows folder selector…");
    try {
      const payload = await api("/api/select-output-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial: el.outputFolder.value || state.lastOutputFolder }),
      });
      if (payload.folder) {
        el.outputFolder.value = payload.folder;
        state.lastOutputFolder = payload.folder;
      }
    } catch (error) { toast(error.message, "error"); }
    finally { hideBusy(); }
  }

  async function generate() {
    const template = selectedTemplate();
    if (!template) return toast("Choose a template.", "error");
    if (!state.uploads.length) return toast("Add at least one replacement label PDF.", "error");
    const mismatches = state.uploads.filter((u) => !sizeMatches(u, template));
    if (mismatches.length) return toast("Remove or correct the label files marked SIZE MISMATCH.", "error");
    if (!el.generateCombined.checked && !el.generateIndividual.checked) return toast("Select at least one output option.", "error");
    if (!el.outputFolder.value.trim()) return toast("Choose an output folder.", "error");
    const mixed = document.querySelector('input[name="arrangement"]:checked')?.value === "mixed";
    if (mixed && state.uploads.length > template.slot_count) {
      return toast(`This template only has ${template.slot_count} positions.`, "error");
    }

    showBusy("GENERATING A5 SHEETS", "Placing vector PDFs and applying the CutContour page border…");
    el.generateButton.disabled = true;
    try {
      const payload = await api("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_id: template.id,
          label_rows: state.uploads.map(rowPayload),
          combine_one_page: mixed,
          generate_combined: el.generateCombined.checked,
          generate_individual: el.generateIndividual.checked,
          combined_name: el.combinedName.value || "Atlas Tool Labels",
          output_folder: el.outputFolder.value,
        }),
      });
      state.lastOutputFolder = payload.output_folder;
      el.resultPanel.classList.remove("hidden");
      el.resultTitle.textContent = `${payload.created.length} FILE${payload.created.length === 1 ? "" : "S"} GENERATED`;
      el.resultText.textContent = `${payload.page_count} A5 page${payload.page_count === 1 ? "" : "s"} created in ${payload.output_folder}`;
      el.resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      toast("A5 label sheets generated successfully.");
    } catch (error) {
      toast(error.message, "error", 9000);
    } finally {
      el.generateButton.disabled = false;
      hideBusy();
    }
  }

  function bindEvents() {
    el.templateSelect.addEventListener("change", () => {
      state.selectedTemplateId = el.templateSelect.value || null;
      updateTemplateSummary();
    });
    el.editTemplateButton.addEventListener("click", () => openTemplateEditor(state.selectedTemplateId));
    $("manageTemplatesButton").addEventListener("click", () => { renderManagerList(); openModal("templateManagerModal"); });
    $("addTemplateButton").addEventListener("click", () => $("newTemplateInput").click());
    $("addBlankTemplateButton").addEventListener("click", addBlankTemplate);
    $("newTemplateInput").addEventListener("change", (event) => addTemplate(event.target.files?.[0]));
    $("importLibraryButton").addEventListener("click", () => $("importLibraryInput").click());
    $("importLibraryInput").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      confirmDialog(
        "RESTORE TEMPLATE LIBRARY?",
        "This will replace the current template library with the selected backup so additions, edits and deletions transfer exactly. The current library will be backed up automatically first.",
        () => importLibrary(file)
      );
    });
    $("exportLibraryButton").addEventListener("click", exportLibrary);

    el.labelDropZone.addEventListener("click", () => el.labelFileInput.click());
    el.labelFileInput.addEventListener("change", (event) => uploadLabels([...event.target.files]));
    ["dragenter", "dragover"].forEach((name) => el.labelDropZone.addEventListener(name, (event) => { event.preventDefault(); el.labelDropZone.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach((name) => el.labelDropZone.addEventListener(name, (event) => { event.preventDefault(); el.labelDropZone.classList.remove("dragover"); }));
    el.labelDropZone.addEventListener("drop", (event) => uploadLabels([...event.dataTransfer.files].filter((f) => f.name.toLowerCase().endsWith(".pdf"))));

    el.generateCombined.addEventListener("change", () => { el.combinedName.disabled = !el.generateCombined.checked; });
    $("chooseFolderButton").addEventListener("click", chooseFolder);
    el.generateButton.addEventListener("click", generate);
    el.openFolderButton.addEventListener("click", async () => {
      try { await api("/api/open-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: state.lastOutputFolder }) }); }
      catch (error) { toast(error.message, "error"); }
    });

    document.querySelectorAll(".modal-close").forEach((button) => button.addEventListener("click", () => closeModal(button.dataset.close)));
    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.addEventListener("mousedown", (event) => { if (event.target === backdrop && backdrop.id !== "confirmModal") closeModal(backdrop.id); }));

    el.editorWidth.addEventListener("change", updateEditorDimensions);
    el.editorHeight.addEventListener("change", updateEditorDimensions);
    el.editorPositionX.addEventListener("change", updateEditorPosition);
    el.editorPositionY.addEventListener("change", updateEditorPosition);
    $("addSlotButton").addEventListener("click", () => {
      if (!state.editor) return;
      const dims = editorDimensionsPt();
      const x = Math.max(0, (state.editor.page_width_pt - dims.width) / 2);
      const y = Math.max(0, (state.editor.page_height_pt - dims.height) / 2);
      state.editor.slots.push({ id: Math.random().toString(36).slice(2, 14), matrix: matrixForBBox(x, y, 0, dims.width, dims.height), rotation: 0 });
      state.editorSelectedSlot = state.editor.slots.length - 1;
      renderEditor();
    });
    el.rotateSlotButton.addEventListener("click", () => {
      if (!state.editor || state.editorSelectedSlot < 0) return;
      const slot = state.editor.slots[state.editorSelectedSlot];
      const dims = editorDimensionsPt();
      const bbox = transformBBox(dims.width, dims.height, slot.matrix);
      slot.rotation = ((slot.rotation || 0) + 90) % 360;
      const nextBBoxW = slot.rotation % 180 === 0 ? dims.width : dims.height;
      const nextBBoxH = slot.rotation % 180 === 0 ? dims.height : dims.width;
      const centerX = bbox.x + bbox.w / 2;
      const centerY = bbox.y + bbox.h / 2;
      const x = Math.min(Math.max(0, centerX - nextBBoxW / 2), state.editor.page_width_pt - nextBBoxW);
      const y = Math.min(Math.max(0, centerY - nextBBoxH / 2), state.editor.page_height_pt - nextBBoxH);
      slot.matrix = matrixForBBox(x, y, slot.rotation, dims.width, dims.height);
      renderEditor();
    });
    el.deleteSlotButton.addEventListener("click", () => {
      if (!state.editor || state.editorSelectedSlot < 0) return;
      state.editor.slots.splice(state.editorSelectedSlot, 1);
      state.editorSelectedSlot = -1;
      renderEditor();
    });
    $("saveTemplateButton").addEventListener("click", saveTemplateEditor);
    $("replaceMasterButton").addEventListener("click", () => $("replaceMasterInput").click());
    $("replaceMasterInput").addEventListener("change", (event) => replaceMaster(event.target.files?.[0]));

    $("confirmCancel").addEventListener("click", () => { state.confirmAction = null; closeModal("confirmModal"); });
    $("confirmAccept").addEventListener("click", async () => {
      const action = state.confirmAction;
      state.confirmAction = null;
      closeModal("confirmModal");
      if (action) await action();
    });

    $("closeAppButton").addEventListener("click", async () => {
      try { await api("/api/shutdown", { method: "POST", body: new Uint8Array([1]) }); } catch (_) {}
      window.close();
      document.body.innerHTML = `<div style="display:grid;place-items:center;height:100vh;background:#050505;color:#eee;font-family:Arial"><div style="text-align:center"><h2 style="color:#e5aa00">ATLAS TOOLS LABEL SHEET BUILDER</h2><p>The application has closed. You can close this window.</p></div></div>`;
    });
  }

  async function init() {
    bindEvents();
    showBusy("STARTING APPLICATION", "Loading the permanent template library…");
    try {
      await loadStatus();
      await loadTemplates();
      customFont=(await api("/api/designer")).custom_font;
      await loadToolTemplates();
      renderUploads();
    } catch (error) {
      toast(error.message, "error", 10000);
    } finally { hideBusy(); }
    window.setInterval(() => fetch("/api/ping").catch(() => {}), 20000);
  }

  init();
})();
