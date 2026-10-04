(() => {
  const products = [
    { code: 'S-01 · EXTERIOR', name: 'Monolith directory sign', location: 'Main vehicle entrance', size: '2400 × 900 mm', material: 'Aluminium tray · printed vinyl', qty: 1, unit: 1895, category: 'exterior', open: true },
    { code: 'S-02 · EXTERIOR', name: 'Post & panel directional signs', location: 'Car park junctions · Locations A–C', size: '1200 × 800 mm', material: 'Aluminium panel · 2 posts', qty: 3, unit: 465, category: 'exterior' },
    { code: 'S-03 · INTERIOR', name: 'Reception feature lettering', location: 'Building 4 · Main reception', size: '1800 × 320 mm', material: 'Built-up acrylic · halo illuminated', qty: 1, unit: 1175, category: 'interior' },
    { code: 'S-04 · INTERIOR', name: 'Door identification plaques', location: 'Units 4–12', size: '210 × 148 mm', material: 'Brushed aluminium · printed', qty: 10, unit: 37.9, category: 'interior' }
  ];
  let discount = 0;
  const money = value => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(value);
  const toast = message => { const node = document.getElementById('toast'); node.textContent = message; node.classList.add('show'); clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('show'), 2600); };

  function render() {
    const host = document.getElementById('lineItems');
    host.innerHTML = '';
    products.forEach((product, index) => {
      const item = document.getElementById('lineItemTemplate').content.firstElementChild.cloneNode(true);
      item.dataset.index = index; item.dataset.category = product.category; item.classList.toggle('open', product.open);
      item.querySelector('.item-code').textContent = product.code;
      item.querySelector('.item-name').textContent = product.name;
      item.querySelector('.item-location').textContent = product.location;
      item.querySelector('.item-size').textContent = product.size;
      item.querySelector('.item-material').textContent = product.material;
      item.querySelector('.qty').value = product.qty;
      item.querySelector('.unit-price').textContent = money(product.unit);
      item.querySelector('.line-total').textContent = money(product.unit * product.qty);
      item.querySelectorAll('.toggle-details').forEach(button => button.addEventListener('click', () => { product.open = !product.open; item.classList.toggle('open', product.open); }));
      item.querySelector('.qty-minus').addEventListener('click', () => updateQty(index, product.qty - 1));
      item.querySelector('.qty-plus').addEventListener('click', () => updateQty(index, product.qty + 1));
      item.querySelector('.qty').addEventListener('change', event => updateQty(index, Number(event.target.value)));
      item.querySelector('.more-btn').addEventListener('click', () => toast(`Actions opened for ${product.code.split(' · ')[0]}`));
      host.append(item);
    });
    document.getElementById('itemCount').textContent = products.length;
    document.getElementById('allCount').textContent = products.length;
    calculate(); applyFilters();
  }

  function updateQty(index, next) { products[index].qty = Math.max(1, Number.isFinite(next) ? next : 1); render(); toast('Quantity and quote totals updated'); }
  function calculate() {
    const productTotal = products.reduce((sum, item) => sum + item.qty * item.unit, 0);
    const subtotal = productTotal + 180 + 980 + 85 - discount;
    const vat = subtotal * .2, total = subtotal + vat, cost = productTotal * .57 + 977;
    const profit = subtotal - cost, margin = profit / subtotal * 100;
    document.getElementById('productTotal').textContent = money(productTotal);
    document.getElementById('discountValue').textContent = discount ? `−${money(discount)}` : '—';
    document.getElementById('subtotal').textContent = money(subtotal);
    document.getElementById('vat').textContent = money(vat);
    document.getElementById('grandTotal').textContent = money(total);
    document.getElementById('estimatedCost').textContent = money(cost);
    document.getElementById('estimatedProfit').textContent = money(profit);
    document.getElementById('marginPercent').textContent = `${margin.toFixed(1)}%`;
    document.querySelector('.margin-track i').style.width = `${Math.min(100, margin * 1.75)}%`;
  }

  function addProduct() {
    products.push({ code: `S-${String(products.length + 1).padStart(2, '0')} · INTERIOR`, name: 'New sign item', location: 'Select a location', size: 'Enter finished size', material: 'Choose materials and finish', qty: 1, unit: 0, category: 'interior', open: true });
    render(); document.querySelector('.line-item:last-child').scrollIntoView({ behavior: 'smooth', block: 'center' }); toast('New sign added to the schedule');
  }

  let activeFilter = 'all';
  function applyFilters() {
    const query = document.getElementById('itemSearch').value.toLowerCase().trim();
    document.querySelectorAll('.line-item').forEach(item => {
      const product = products[Number(item.dataset.index)];
      const matchesFilter = activeFilter === 'all' || product.category === activeFilter;
      const matchesSearch = !query || `${product.code} ${product.name} ${product.location} ${product.material}`.toLowerCase().includes(query);
      item.classList.toggle('hidden-item', !matchesFilter || !matchesSearch);
    });
  }

  document.getElementById('addItem').addEventListener('click', addProduct);
  document.getElementById('addItemBottom').addEventListener('click', addProduct);
  document.getElementById('itemSearch').addEventListener('input', applyFilters);
  document.querySelectorAll('.filter-btn').forEach(button => button.addEventListener('click', () => { activeFilter = button.dataset.filter; document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b === button)); applyFilters(); }));
  document.getElementById('importSchedule').addEventListener('click', () => toast('Schedule importer ready for CSV or XLSX files'));
  document.getElementById('discountButton').addEventListener('click', () => { discount = discount ? 0 : 250; calculate(); toast(discount ? 'Trade discount of £250 applied' : 'Discount removed'); });
  document.getElementById('reviewQuote').addEventListener('click', () => { window.scrollTo({ top: 0, behavior: 'smooth' }); toast('Quote checked — all required specifications are complete'); });
  const dialog = document.getElementById('sendDialog');
  document.getElementById('sendQuote').addEventListener('click', () => dialog.showModal());
  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.dialog-cancel').addEventListener('click', () => dialog.close());
  dialog.querySelector('.dialog-confirm').addEventListener('click', () => { dialog.close(); document.querySelector('.status').textContent = 'SENT'; document.querySelector('.status').style.background = '#e5f3ee'; document.querySelector('.status').style.color = '#096b5b'; toast('Quote sent to Amelia Hart'); });
  render();
})();
