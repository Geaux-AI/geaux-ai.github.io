/**
 * Google Apps Script guard for the bookkeeping ledger.
 * Paste into Extensions -> Apps Script on the imported Google Sheet, then
 * add an installable onEdit trigger (or run setup() once).
 *
 * It does two things the agent shouldn't be trusted to enforce alone:
 *   1. Flags duplicate documents by Source_Doc_Hash (belt-and-suspenders with Dup_Check).
 *   2. Locks a row once it's Posted-QBO so a Posted transaction can't be silently edited.
 *
 * Column letters match Bookkeeping-Ledger-Template.xlsx (Transactions tab).
 */

var SHEET = 'Transactions';
var COL = { HASH: 10, STATUS: 12, QBO_ID: 13 }; // J, L, M (1-indexed)
var STATUS_POSTED = 'Posted-QBO';

function onEditGuard(e) {
  var sh = e.range.getSheet();
  if (sh.getName() !== SHEET) return;
  var row = e.range.getRow();
  if (row < 2) return;

  // 1. Duplicate document hash -> note on the cell
  if (e.range.getColumn() === COL.HASH && e.value) {
    var hashes = sh.getRange(2, COL.HASH, sh.getLastRow() - 1, 1).getValues().flat();
    var count = hashes.filter(function (h) { return h === e.value; }).length;
    if (count > 1) {
      e.range.setNote('DUPLICATE document hash — this file was already uploaded. Do not approve without checking.');
      e.range.setBackground('#f4cccc');
    }
  }

  // 2. Lock a Posted-QBO row from further edits (protect the audit trail)
  var status = sh.getRange(row, COL.STATUS).getValue();
  var qboId = sh.getRange(row, COL.QBO_ID).getValue();
  if (status === STATUS_POSTED && qboId) {
    // If someone edits a posted row, warn loudly.
    if (e.range.getColumn() !== COL.STATUS) {
      SpreadsheetApp.getActiveSpreadsheet().toast(
        'Row ' + row + ' is Posted to QuickBooks. Edits here will NOT sync to QuickBooks.',
        'Posted row edited', 8);
    }
  }
}

function setup() {
  var ss = SpreadsheetApp.getActive();
  ScriptApp.newTrigger('onEditGuard').forSpreadsheet(ss).onEdit().create();
  SpreadsheetApp.getUi().alert('Bookkeeping guard installed.');
}
