/**
 * Brand Intelligence — Google Sheets bridge (paste into Extensions → Apps Script of your sheet).
 * 1) Project Settings → Script properties → add  SECRET = <long random string>  (same value as GitHub secret SHEETS_SECRET)
 * 2) Deploy → New deployment → Web app → Execute as: Me · Who has access: Anyone → copy URL → GitHub secret SHEETS_WEBAPP_URL
 * doPost: the pipeline writes rows (requires SECRET).
 * doGet : the Viewer reads published news as JSON (read-only, no secrets, only News columns).
 */
function doPost(e) {
  var body = JSON.parse(e.postData.contents);
  var secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  if (!secret || body.secret !== secret) return out_({ok: false, error: 'unauthorized'});
  var lock = LockService.getScriptLock(); lock.waitLock(30000);
  try {
    var ss = SpreadsheetApp.getActive();
    var sh = ss.getSheetByName(body.tab) || ss.insertSheet(body.tab);
    var cols = body.columns, rows = body.rows;
    if (body.mode === 'replace') {
      sh.clearContents();
      sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
      if (rows.length) sh.getRange(2, 1, rows.length, cols.length).setValues(rows);
      sh.setFrozenRows(1);
      return out_({ok: true, written: rows.length});
    }
    if (sh.getLastRow() === 0) {
      sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold'); sh.setFrozenRows(1);
    }
    var header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    cols.forEach(function (c) { if (header.indexOf(c) < 0) { header.push(c); sh.getRange(1, header.length).setValue(c).setFontWeight('bold'); } });
    var keyIdx = header.indexOf(body.key);
    var existing = {};
    if (sh.getLastRow() > 1) {
      sh.getRange(2, keyIdx + 1, sh.getLastRow() - 1, 1).getValues().forEach(function (r, i) { existing[r[0]] = i + 2; });
    }
    var appends = [], updated = 0;
    rows.forEach(function (r) {
      var line = header.map(function (h) { var j = cols.indexOf(h); return j < 0 ? '' : r[j]; });
      var k = r[cols.indexOf(body.key)];
      if (existing[k]) { sh.getRange(existing[k], 1, 1, header.length).setValues([line]); updated++; }
      else appends.push(line);
    });
    if (appends.length) sh.getRange(sh.getLastRow() + 1, 1, appends.length, header.length).setValues(appends);
    return out_({ok: true, appended: appends.length, updated: updated});
  } finally { lock.releaseLock(); }
}

function doGet(e) {
  var days = Number((e && e.parameter && e.parameter.days) || 7);
  var sh = SpreadsheetApp.getActive().getSheetByName('News');
  if (!sh || sh.getLastRow() < 2) return out_({ok: true, items: []});
  var data = sh.getDataRange().getValues(), header = data.shift();
  var since = new Date(Date.now() - days * 86400000).toISOString();
  var items = data.map(function (r) { var o = {}; header.forEach(function (h, i) { o[h] = r[i]; }); return o; })
    .filter(function (o) { return String(o.collected_at) >= since && !o.duplicate_of; });
  return out_({ok: true, generated: new Date().toISOString(), items: items});
}

function out_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
