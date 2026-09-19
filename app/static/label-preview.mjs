export function fitScale(pw,ph,w,h,margin=12){return Math.max(.001,Math.min(Math.max(1,w-margin*2)/pw,Math.max(1,h-margin*2)/ph));}
export class LabelPreview {
 constructor(container,canvas){this.container=container;this.canvas=canvas;this.page=null;this.doc=null;this.revision=0;this.chain=Promise.resolve();this.task=null;this.observer=new ResizeObserver(()=>this.render().catch(()=>{}));this.observer.observe(container);}
 clear(){this.revision++;this.page=null;this.task?.cancel();this.container.classList.add('hidden');}
 async show(blob){
  const revision=++this.revision;const pdfjs=await import('/static/pdfjs/pdf.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc='/static/pdfjs/pdf.worker.mjs';
  const doc=await pdfjs.getDocument({data:new Uint8Array(await blob.arrayBuffer()),cMapUrl:'/static/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/pdfjs/standard_fonts/',wasmUrl:'/static/pdfjs/wasm/',iccUrl:'/static/pdfjs/iccs/'}).promise;
  const page=await doc.getPage(1);if(revision!==this.revision){await doc.destroy();return;}
  this.task?.cancel();await this.chain.catch(()=>{});if(this.doc)await this.doc.destroy();
  if(revision!==this.revision){await doc.destroy();return;}
  this.doc=doc;this.page=page;this.container.classList.remove('hidden');await this.render();
  let pending;do{pending=this.chain;await pending;}while(pending!==this.chain);
 }
 render(){
  if(this.page && !this.container.classList.contains('hidden')){
   const b=this.page.getViewport({scale:1});const scale=fitScale(b.width,b.height,this.container.clientWidth,this.container.clientHeight);
   this.canvas.style.width=b.width*scale+'px';this.canvas.style.height=b.height*scale+'px';
  }
  this.task?.cancel();this.chain=this.chain.catch(()=>{}).then(async()=>{
   const page=this.page;if(!page || this.container.classList.contains('hidden'))return;
   const base=page.getViewport({scale:1});const scale=fitScale(base.width,base.height,this.container.clientWidth,this.container.clientHeight);
   const viewport=page.getViewport({scale});const dpr=Math.min(window.devicePixelRatio||1,2);
   this.canvas.style.width=viewport.width+'px';this.canvas.style.height=viewport.height+'px';
   const surface=document.createElement('canvas');surface.width=Math.ceil(viewport.width*dpr);surface.height=Math.ceil(viewport.height*dpr);
   this.task=page.render({canvasContext:surface.getContext('2d'),viewport,transform:[dpr,0,0,dpr,0,0]});
   try{await this.task.promise;if(page===this.page){this.canvas.width=surface.width;this.canvas.height=surface.height;this.canvas.getContext('2d').drawImage(surface,0,0);}}
   catch(e){if(e.name!=='RenderingCancelledException')throw e;}finally{this.task=null;}
  });return this.chain;
 }
}
