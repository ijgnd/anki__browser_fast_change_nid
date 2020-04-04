# Add-on for Anki 2.1
#
# Copyright (c) 2014 by Simone Gaiarin <simgunz@gmail.com>
#               2017 Glutanimate
#               2020- by ijgnd
#
#                                                                     
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or   
# (at your option) any later version.                                 
#                                                                     
# This program is distributed in the hope that it will be useful,     
# but WITHOUT ANY WARRANTY; without even the implied warranty of      
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the       
# GNU General Public License for more details.                        
#                                                                     
# You should have received a copy of the GNU General Public License   
# along with this program; if not, see <http://www.gnu.org/licenses/>.


from pprint import pprint as pp

from anki import hooks
from anki.utils import ids2str

from aqt import gui_hooks
from aqt import mw
from aqt.qt import (
    QAction
)
from aqt.browser import Browser
from aqt.utils import shortcut, showInfo, tooltip, askUser, getText


def gc(arg, fail=False):
    conf = mw.addonManager.getConfig(__name__)
    if conf:
        return conf.get(arg, fail)
    return fail


def adjust_contextmenu(browser, val):
    browser.form.nid_mvuponeAction.setEnabled(val)
    browser.form.nid_mvuponeAction.setVisible(val)
    browser.form.nid_mvdownoneAction.setEnabled(val)
    browser.form.nid_mvdownoneAction.setVisible(val)


def onSortChanged(browser, idx, ord):
    # context menu is setup when browser is loaded so I can't dynamically add my actions
    sortedByNid = browser.model.activeCols[idx] == 'nid'
    val = sortedByNid and mw.col.conf.get("advbrowse_uniqueNote", False)
    adjust_contextmenu(browser, val)
Browser.onSortChanged = hooks.wrap(Browser.onSortChanged, onSortChanged)


def setupRepositionActions(browser):
    """Add actions to the browser menu to move the notes up and down"""
    # Set the actions active only if the cards are sorted by date created. This is necessary because 
    # the reposition is done considering the current ordering in the browser
    browser.form.nid_mvuponeAction = QAction("nid - move one up", browser)
    cut_up = gc("shortcut up")
    if cut_up:
        browser.form.nid_mvuponeAction.setShortcut(shortcut(cut_up))
    browser.form.nid_mvuponeAction.triggered.connect(lambda _, b=browser: moveNoteUp(b))
    
    browser.form.nid_mvdownoneAction = QAction("nid - move one down", browser)
    cut_down = gc("shortcut down")
    if cut_down:
        browser.form.nid_mvdownoneAction.setShortcut(shortcut(cut_down))
    browser.form.nid_mvdownoneAction.triggered.connect(lambda _, b=browser: moveNoteDown(b))

    browser.form.nid_change_Action = QAction("change nid", browser)
    change_nid = gc("shortcut change nid")
    if change_nid:
        browser.form.nid_change_Action.setShortcut(shortcut(change_nid))
    browser.form.nid_change_Action.triggered.connect(lambda _, b=browser: update_nid(b))
    
    browser.form.menu_Cards.addSeparator()
    browser.form.menu_Cards.addAction(browser.form.nid_mvuponeAction)
    browser.form.menu_Cards.addAction(browser.form.nid_mvdownoneAction)
    browser.form.menu_Cards.addAction(browser.form.nid_change_Action)

    # for the initial view
    sortedByNid = browser.col.conf["sortType"] == 'nid'
    if not (sortedByNid and mw.col.conf.get("advbrowse_uniqueNote", False)):
        browser.form.nid_mvuponeAction.setEnabled(False)
        browser.form.nid_mvuponeAction.setVisible(False)
        browser.form.nid_mvdownoneAction.setEnabled(False)
        browser.form.nid_mvdownoneAction.setVisible(False)
gui_hooks.browser_menus_did_init.append(setupRepositionActions)


def moveNoteUp(self):
    moveNote(self, -1)


def moveNoteDown(self):
    moveNote(self, 1)


def moveNote(self, pos):
    srows = self.form.tableView.selectionModel().selectedRows()

    sel_cids = self.selectedCards()
    if not len(sel_cids):
        tooltip("you must select at least one card(note). Aborting ...")
        return

    #Get the list of indexes of the selcted rows
    srowsidxes = []
    for crow in srows:
        srowsidxes.append(crow.row())
    pp(srowsidxes)

    #Check if the first (last) selected row is the first (last) on the table
    #and return in that case because it cannot moved up (down)
    if pos == -1:
        srowidx = min(srowsidxes)
        if srowidx == 0:
            return
    elif pos == 1:
        srowidx = max(srowsidxes)
        if srowidx == len(self.model.cards)-1:
            return

    # TODO cleanup the rest
    #Get the next nid
    startidx = srowidx+pos
    pp(f"startidx: {startidx}")
    neighboring_cid = self.model.cards[startidx]
    neighboring_card = self.model.cardObjs[neighboring_cid]
    neighboring_nid = neighboring_card.nid

    note_pool = mw.col.db.list("select id from notes") 
    note_pool.sort()

    if self.col.conf['sortBackwards']:
        inverted = -1
    else:
        inverted = 1
    
    neighboring_note_idx = note_pool.index(neighboring_nid)
    if pos == -1:
        neigh_neigh_nid = note_pool[neighboring_note_idx + (-1 * inverted)]
    else:
        neigh_neigh_nid = note_pool[neighboring_note_idx + (1 * inverted)]
    diff = max(neighboring_nid, neigh_neigh_nid) - min(neighboring_nid, neigh_neigh_nid)
    if diff-3 < len(sel_cids):
        msg = ("Error: Not enough free new nid values to use. Adjust the neighboring "
               "nid manually and try again. For complex reorganizaton tasks use the "
               "add-on Note-Organizer. Aborting ...")
        tooltip(msg)
        return
    spacing = min(int((diff-2)/len(sel_cids)), 40)
    print(f"spacing is: {spacing}")
    print(f"selcids are: {sel_cids}")
    self.model.beginReset()
    self.mw.checkpoint("Rearrange")

    changes = {}
    for idx, cid in enumerate(reversed(sel_cids)):
        cur_card = mw.col.getCard(cid)
        cur_nid = cur_card.nid
        new_nid = neighboring_nid + (pos * inverted * (idx+1) * spacing)  # lists are zero indexed
        changes[cur_nid] = new_nid
    print("___changedict:")
    pp(changes)
    for new in changes.values():
        if noteExists(new):
            msg = f'Error. new nid {new} already exists. Aborting ...'
            print(msg)
            tooltip(msg)
            return
    for new, old in changes.items():
        change_nid(new, old)
    self.search()
    self.mw.requireReset()
    self.model.endReset()



def noteExists(nid):
    """Checks the database to see whether the nid is actually assigned"""
    return mw.col.db.scalar(
        """select id from notes where id = ?""", nid)


def change_nid(old_nid, new_nid):
    if noteExists(new_nid):
        return
    else:
        # from glutanimate's note organizer
        # mw.col.db.execute(
        #     """update notes set id=? where id = ?""", new_nid, old_nid)
        # mw.col.db.execute(
        #     """update cards set nid=? where nid = ?""", new_nid, old_nid)

        """
        # mw.col.modSchema(check=True)  # this triggers a full sync: 
        that's what glutanimate's note-organizer from 2017 uses
        in 2020 Arthur extended Advanced Browser with a nid-change function , see
        https://github.com/hssm/advanced-browser/commit/7fba8f30f0ebd12b2f458f8a56ec7c6c068ddf24
        His code doesn't require a full sync (he said in a direct reddit message)
        https://github.com/hssm/advanced-browser/blob/92ffac0555a5d7058ba0865c63c2e8cb52d8dbc6/advancedbrowser/advancedbrowser/internal_fields.py#L47
        Arthur's code is:
            if not askUser(_("Do you really want to change the id of the note ? This may create problems during synchronisation if the note has been modified on another computer.")):
                        return False
            old_nid = c.nid
            n = c.note()
            cards = n.cards()
            n.id = value
            n.flush()
            for card in cards:
                card.nid = value
                card.flush()
            c.col._remNotes([old_nid])
        So Arthur just adds "col._remNotes([old_nid])"
        """
        n = mw.col.getNote(old_nid)
        cards = n.cards()
        n.id = new_nid
        n.flush()
        for card in cards:
            card.nid = new_nid
            card.flush()
        mw.col._remNotes([old_nid])
        return new_nid


def update_nid(browser):
    sel_cids = browser.selectedCards()
    if len(sel_cids) != 1:
        tooltip("only select one card (note). Aborting ...")
        return
    cur_card = mw.col.getCard(sel_cids[0])
    old_nid = cur_card.nid

    # TODO: replace with QTimeEdit, so that alternatively I can more human friendly enter time values
    #  https://doc.qt.io/qt-5/qtimeedit.html
    newstr, ok = getText("new nid", default=str(old_nid))
    if not ok: 
        return
    try:
        new_nid = int(newstr)
    except:
        tooltip("invalid values entered. numbers only. Aborting ...")
        return
    if not len(str(new_nid)) == 13:
        msg = (f"invalid values entered. nid must consist of 13 integers, you "
               f"entered {len(str(new_nid))}. Aborting ...")
        tooltip(msg)
        return
    if noteExists(new_nid):
        tooltip("entered value exists. Try again. Aborting ...")
        return        
    if not askUser(f"Change nid {old_nid} to {new_nid}?"):
        return
    browser.model.beginReset()
    browser.mw.checkpoint("Rearrange")
    change_nid(old_nid, new_nid)
    browser.search()
    browser.mw.requireReset()
    browser.model.endReset()
