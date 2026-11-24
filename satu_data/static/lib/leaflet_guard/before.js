/* Satu Data: simpan Leaflet yang sudah dimuat modul lain (beserta plugin-nya),
 * sebelum salinan Leaflet milik satu_data menimpa window.L.
 * File ini sengaja di static/lib agar tidak ditranspilasi sebagai modul Odoo. */
window.__satuDataLeafletSebelumnya = window.L;
