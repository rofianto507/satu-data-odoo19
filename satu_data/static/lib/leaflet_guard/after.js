/* Satu Data: bila Leaflet sudah ada sebelumnya, kembalikan window.L ke instance
 * itu agar plugin yang menempel padanya (mis. markercluster) tetap tersedia. */
if (window.__satuDataLeafletSebelumnya) {
    window.L = window.__satuDataLeafletSebelumnya;
}
delete window.__satuDataLeafletSebelumnya;
