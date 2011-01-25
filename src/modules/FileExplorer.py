# -*- coding: utf-8 -*-
#
# Author: Ingelrest François (Francois.Ingelrest@gmail.com)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import cgi, gtk, gui.window, media, modules, os, tools, urllib

from gui     import fileChooser, help, extTreeview, extListview, selectPath
from tools   import consts, prefs
from media   import playlist
from gettext import gettext as _
from os.path import isdir, isfile
from gobject import idle_add, TYPE_STRING, TYPE_INT

MOD_INFO = ('File Explorer', _('File Explorer'), _('Browse your file system'), [], True, True)
MOD_L10N = MOD_INFO[modules.MODINFO_L10N]

# Default preferences
PREFS_DEFAULT_MEDIA_FOLDERS     = {_('Home'): consts.dirBaseUsr, _('Root'): '/'}    # List of media folders that are used as roots for the file explorer
PREFS_DEFAULT_ADD_BY_FILENAME   = False                                             # True if files should be added to the playlist by their filename
PREFS_DEFAULT_SHOW_HIDDEN_FILES = False                                             # True if hidden files should be shown


# The format of a row in the treeview
(
    ROW_PIXBUF,    # Item icon
    ROW_NAME,      # Item name
    ROW_TYPE,      # The type of the item (e.g., directory, file)
    ROW_FULLPATH   # The full path to the item
) = range(4)


# The possible types for a node of the tree
(
    TYPE_DIR,   # A directory
    TYPE_FILE,  # A media file
    TYPE_NONE   # A fake item, used to display a '+' in front of a directory when needed
) = range(3)


class FileExplorer(modules.Module):
    """ This explorer lets the user browse the disk from a given root directory (e.g., ~/, /) """

    def __init__(self):
        """ Constructor """
        modules.Module.__init__(self, (consts.MSG_EVT_APP_STARTED, consts.MSG_EVT_EXPLORER_CHANGED, consts.MSG_EVT_APP_QUIT))


    def onModLoaded(self):
        """ The module has been loaded """
        self.tree            = None
        self.cfgWin          = None
        self.folders         = prefs.get(__name__, 'media-folders', PREFS_DEFAULT_MEDIA_FOLDERS)
        self.scrolled        = gtk.ScrolledWindow()
        self.currRoot        = None
        self.addByFilename   = prefs.get(__name__, 'add-by-filename',  PREFS_DEFAULT_ADD_BY_FILENAME)
        self.showHiddenFiles = prefs.get(__name__, 'show-hidden-files', PREFS_DEFAULT_SHOW_HIDDEN_FILES)

        self.scrolled.set_shadow_type(gtk.SHADOW_IN)
        self.scrolled.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.scrolled.show()

        for name in self.folders:
            modules.postMsg(consts.MSG_CMD_EXPLORER_ADD, {'modName': MOD_L10N, 'expName': name, 'icon': None, 'widget': self.scrolled})


    def onModUnloaded(self):
        """ The module is going to be unloaded """
        prefs.set(__name__, 'media-folders',     self.folders)
        prefs.set(__name__, 'add-by-filename',   self.addByFilename)
        prefs.set(__name__, 'show-hidden-files', self.showHiddenFiles)

        # Save the state of the current tree if needed
        if self.currRoot is not None:
            savedStates = prefs.get(__name__, 'saved-states', {})
            savedStates[self.currRoot] = {
                                            'tree-state':     self.dumpTree(),
                                            'selected-paths': self.tree.getSelectedPaths(),
                                            'vscrollbar-pos': self.scrolled.get_vscrollbar().get_value(),
                                            'hscrollbar-pos': self.scrolled.get_hscrollbar().get_value(),
                                         }
            prefs.set(__name__, 'saved-states', savedStates)


    def dumpTree(self, path=None):
        """ Recursively dump the given tree starting at path (None for the root of the tree) """
        list = []

        for child in self.tree.iterChildren(path):
            row = self.tree.getRow(child)

            if self.tree.getNbChildren(child) == 0: grandChildren = None
            elif self.tree.row_expanded(child):     grandChildren = self.dumpTree(child)
            else:                                   grandChildren = []

            list.append([(row[ROW_NAME], row[ROW_TYPE], row[ROW_FULLPATH]), grandChildren])

        return list


    def restoreTree(self, dump, parent=None):
        """ Recursively restore the dump under the given parent (None for the root of the tree) """
        for item in dump:
            (name, type, path) = item[0]

            if type == TYPE_FILE:
                self.tree.appendRow((consts.icoMediaFile, name, TYPE_FILE, path), parent)
            else:
                newNode = self.tree.appendRow((consts.icoDir, name, TYPE_DIR, path), parent)

                if item[1] is not None:
                    fakeChild = self.tree.appendRow((consts.icoDir, '', TYPE_NONE, ''), newNode)

                    if len(item[1]) != 0:
                        # We must expand the row before adding the real children, but this works only if there is already at least one child
                        self.tree.expandRow(newNode)
                        self.restoreTree(item[1], newNode)
                        self.tree.removeRow(fakeChild)


    def sortKey(self, row):
        """ Key function used to compare two rows of the tree """
        return row[ROW_NAME].lower()


    def setShowHiddenFiles(self, showHiddenFiles):
        """ Show/hide hidden files """
        if showHiddenFiles != self.showHiddenFiles:
            # Update the configuration window if needed
            if self.cfgWin is not None and self.cfgWin.isVisible():
                self.cfgWin.getWidget('chk-hidden').set_active(showHiddenFiles)

            self.showHiddenFiles = showHiddenFiles
            self.refresh()


    def play(self, replace, path=None):
        """
            Replace/extend the tracklist
            If 'path' is None, use the current selection
        """
        if path is None: tracks = media.getTracks([row[ROW_FULLPATH] for row in self.tree.getSelectedRows()], self.addByFilename)
        else:            tracks = media.getTracks([self.tree.getRow(path)[ROW_FULLPATH]], self.addByFilename)

        if replace: modules.postMsg(consts.MSG_CMD_TRACKLIST_SET, {'tracks': tracks, 'playNow': True})
        else:       modules.postMsg(consts.MSG_CMD_TRACKLIST_ADD, {'tracks': tracks})


    def renameFolder(self, oldName, newName):
        """ Rename a folder """
        self.folders[newName] = self.folders[oldName]
        del self.folders[oldName]

        savedStates = prefs.get(__name__, 'saved-states', {})
        if oldName in savedStates:
            savedStates[newName] = savedStates[oldName]
            del savedStates[oldName]
            prefs.set(__name__, 'saved-states', savedStates)

        modules.postMsg(consts.MSG_CMD_EXPLORER_RENAME,   {'modName': MOD_L10N, 'expName': oldName, 'newExpName': newName})


    # --== Tree management ==--


    def startLoading(self, row):
        """ Tell the user that the contents of row is being loaded """
        name = self.tree.getItem(row, ROW_NAME)
        self.tree.setItem(row, ROW_NAME, '%s  <span size="smaller" foreground="#909090">%s</span>' % (name, _('loading...')))


    def stopLoading(self, row):
        """ Tell the user that the contents of row has been loaded"""
        name  = self.tree.getItem(row, ROW_NAME)
        index = name.find('<')

        if index != -1:
            self.tree.setItem(row, ROW_NAME, name[:index-2])


    def getDirContents(self, directory):
        """ Return a tuple of sorted rows (directories, playlists, mediaFiles) for the given directory """
        playlists   = []
        mediaFiles  = []
        directories = []

        for (file, path) in tools.listDir(directory, self.showHiddenFiles):
            if isdir(path):
                directories.append((consts.icoDir, cgi.escape(unicode(file, errors='replace')), TYPE_DIR, path))
            elif isfile(path):
                if media.isSupported(file):
                    mediaFiles.append((consts.icoMediaFile, cgi.escape(unicode(file, errors='replace')), TYPE_FILE, path))
                elif playlist.isSupported(file):
                    playlists.append((consts.icoMediaFile, cgi.escape(unicode(file, errors='replace')), TYPE_FILE, path))

        playlists.sort(key=self.sortKey)
        mediaFiles.sort(key=self.sortKey)
        directories.sort(key=self.sortKey)

        return (directories, playlists, mediaFiles)


    def exploreDir(self, parent, directory, fakeChild=None):
        """
            List the contents of the given directory and append it to the tree as a child of parent
            If fakeChild is not None, remove it when the real contents has been loaded
        """
        directories, playlists, mediaFiles = self.getDirContents(directory)

        self.tree.appendRows(directories, parent)
        self.tree.appendRows(playlists,   parent)
        self.tree.appendRows(mediaFiles,  parent)

        if fakeChild is not None:
            self.tree.removeRow(fakeChild)

        idle_add(self.updateDirNodes(parent).next)


    def updateDirNodes(self, parent):
        """ This generator updates the directory nodes, based on whether they should be expandable """
        for child in self.tree.iterChildren(parent):
            # Only directories need to be updated and since they all come first, we can stop as soon as we find something else
            if self.tree.getItem(child, ROW_TYPE) != TYPE_DIR:
                break

            # Make sure it's readable
            directory  = self.tree.getItem(child, ROW_FULLPATH)
            hasContent = False
            if os.access(directory, os.R_OK | os.X_OK):
                for (file, path) in tools.listDir(directory, self.showHiddenFiles):
                    if isdir(path) or (isfile(path) and (media.isSupported(file) or playlist.isSupported(file))):
                        hasContent = True
                        break

            # Append/remove children if needed
            if hasContent and self.tree.getNbChildren(child) == 0:      self.tree.appendRow((consts.icoDir, '', TYPE_NONE, ''), child)
            elif not hasContent and self.tree.getNbChildren(child) > 0: self.tree.removeAllChildren(child)

            yield True

        if parent is not None:
            self.stopLoading(parent)

        yield False


    def refresh(self, treePath=None):
        """ Refresh the tree, starting from treePath """
        if treePath is None: directory = self.folders[self.currRoot]
        else:                directory = self.tree.getItem(treePath, ROW_FULLPATH)

        directories, playlists, mediaFiles = self.getDirContents(directory)

        disk                   = directories + playlists + mediaFiles
        diskIndex              = 0
        childIndex             = 0
        childLeftIntentionally = False

        while diskIndex < len(disk):
            rowPath = self.tree.getChild(treePath, childIndex)

            # Did we reach the end of the tree?
            if rowPath is None:
                break

            file      = disk[diskIndex]
            cmpResult = cmp(self.sortKey(self.tree.getRow(rowPath)), self.sortKey(file))

            if cmpResult < 0:
                # We can't remove the only child left, to prevent the node from being closed automatically
                if self.tree.getNbChildren(treePath) == 1:
                    childLeftIntentionally = True
                    break

                self.tree.removeRow(rowPath)
            else:
                if cmpResult > 0:
                    self.tree.insertRowBefore(file, treePath, rowPath)
                diskIndex  += 1
                childIndex += 1

        # If there are tree rows left, all the corresponding files are no longer there
        if not childLeftIntentionally:
            while childIndex < self.tree.getNbChildren(treePath):
                self.tree.removeRow(self.tree.getChild(treePath, childIndex))

        # Disk files left?
        while diskIndex < len(disk):
            self.tree.appendRow(disk[diskIndex], treePath)
            diskIndex += 1

        # Deprecated child left? (must be done after the addition of left disk files)
        if childLeftIntentionally:
            self.tree.removeRow(self.tree.getChild(treePath, 0))

        # Update nodes' appearance
        if len(directories) != 0:
            idle_add(self.updateDirNodes(treePath).next)

        # Recursively refresh expanded rows
        for child in self.tree.iterChildren(treePath):
            if self.tree.row_expanded(child):
                idle_add(self.refresh, child)


    # --== GTK handlers ==--


    def onMouseButton(self, tree, event, path):
        """ A mouse button has been pressed """
        if event.button == 3:
            self.onShowPopupMenu(tree, event.button, event.time, path)
        elif path is not None:
            if event.button == 2:
                self.play(False, path)
            elif event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
                if   tree.getItem(path, ROW_PIXBUF) != consts.icoDir: self.play(True)
                elif tree.row_expanded(path):                         tree.collapse_row(path)
                else:                                                 tree.expand_row(path, False)


    def onShowPopupMenu(self, tree, button, time, path):
        """ Show a popup menu """
        popup = gtk.Menu()

        # Play selection
#        play = gtk.ImageMenuItem(gtk.STOCK_MEDIA_PLAY)
#        play.set_sensitive(path is not None)
#        play.connect('activate', lambda widget: self.play(True))
#        popup.append(play)

        # Add selection
        add = gtk.ImageMenuItem(gtk.STOCK_ADD)
        add.set_sensitive(path is not None)
        add.connect('activate', lambda widget: self.play(False))
        popup.append(add)

        popup.append(gtk.SeparatorMenuItem())

        # Collapse all nodes
        collapse = gtk.ImageMenuItem(_('Collapse all'))
        collapse.set_image(gtk.image_new_from_stock(gtk.STOCK_CLEAR, gtk.ICON_SIZE_MENU))
        collapse.connect('activate', lambda widget: tree.collapse_all())
        popup.append(collapse)

        # Refresh the library
        refresh = gtk.ImageMenuItem(gtk.STOCK_REFRESH)
        refresh.connect('activate', lambda widget: self.refresh())
        popup.append(refresh)

        popup.append(gtk.SeparatorMenuItem())

        # Show hidden files
        hidden = gtk.CheckMenuItem(_('Show hidden files'))
        hidden.set_active(self.showHiddenFiles)
        hidden.connect('toggled', lambda item: self.setShowHiddenFiles(item.get_active()))
        popup.append(hidden)

        popup.show_all()
        popup.popup(None, None, None, button, time)


    def onKeyPressed(self, tree, event):
        """ A key has been pressed """
        keyname = gtk.gdk.keyval_name(event.keyval)

        if keyname == 'F5':       self.refresh()
        elif keyname == 'plus':   tree.expandRows()
        elif keyname == 'Left':   tree.collapseRows()
        elif keyname == 'Right':  tree.expandRows()
        elif keyname == 'minus':  tree.collapseRows()
        elif keyname == 'space':  tree.switchRows()
        elif keyname == 'Return': self.play(True)


    def onRowExpanded(self, tree, path):
        """ Replace the fake child by the real children """
        self.startLoading(path)
        idle_add(self.exploreDir, path, tree.getItem(path, ROW_FULLPATH), tree.getChild(path, 0))


    def onRowCollapsed(self, tree, path):
        """ Replace all children by a fake child """
        tree.removeAllChildren(path)
        tree.appendRow((consts.icoDir, '', TYPE_NONE, ''), path)


    def onDragDataGet(self, tree, context, selection, info, time):
        """ Provide information about the data being dragged """
        selection.set('text/uri-list', 8, ' '.join([urllib.pathname2url(file) for file in [row[ROW_FULLPATH] for row in tree.getSelectedRows()]]))


   # --== Message handler ==--


    def handleMsg(self, msg, params):
        """ Handle messages sent to this module """
        if msg == consts.MSG_EVT_EXPLORER_CHANGED and params['modName'] == MOD_L10N and self.currRoot != params['expName']:
            newRoot = params['expName']

            # Create the tree if needed (this is done only the very first time)
            if self.tree is None:
                columns = (('',   [(gtk.CellRendererPixbuf(), gtk.gdk.Pixbuf), (gtk.CellRendererText(), TYPE_STRING)], True),
                           (None, [(None, TYPE_INT)],                                                                  False),
                           (None, [(None, TYPE_STRING)],                                                               False))

                self.tree = extTreeview.ExtTreeView(columns, True)

                self.scrolled.add(self.tree)
                self.tree.setDNDSources([consts.DND_TARGETS[consts.DND_DAP_URI]])
                self.tree.connect('drag-data-get', self.onDragDataGet)
                self.tree.connect('key-press-event', self.onKeyPressed)
                self.tree.connect('exttreeview-button-pressed', self.onMouseButton)
                self.tree.connect('exttreeview-row-collapsed', self.onRowCollapsed)
                self.expandedHandler = self.tree.connect('exttreeview-row-expanded', self.onRowExpanded)

            savedStates = prefs.get(__name__, 'saved-states', {})

            # Save the current state if needed
            if self.currRoot is not None:
                savedStates[self.currRoot] = {
                                                'tree-state':     self.dumpTree(),
                                                'selected-paths': self.tree.getSelectedPaths(),
                                                'vscrollbar-pos': self.scrolled.get_vscrollbar().get_value(),
                                                'hscrollbar-pos': self.scrolled.get_hscrollbar().get_value(),
                                             }
                prefs.set(__name__, 'saved-states', savedStates)
                self.tree.clear()

            self.currRoot = newRoot

            if newRoot not in savedStates:
                self.exploreDir(None, self.folders[self.currRoot])
                if len(self.tree) != 0:
                    self.tree.scroll_to_cell(0)
            else:
                savedState = savedStates[newRoot]

                self.tree.disconnect(self.expandedHandler)
                self.restoreTree(savedState['tree-state'])
                self.expandedHandler  = self.tree.connect('exttreeview-row-expanded', self.onRowExpanded)

                idle_add(self.scrolled.get_vscrollbar().set_value, savedState['vscrollbar-pos'])
                idle_add(self.scrolled.get_hscrollbar().set_value, savedState['hscrollbar-pos'])
                idle_add(self.tree.selectPaths, savedState['selected-paths'])
                idle_add(self.refresh)

        elif msg == consts.MSG_EVT_APP_STARTED:
            self.onModLoaded()
        elif msg == consts.MSG_EVT_APP_QUIT:
            self.onModUnloaded()


    # --== Configuration ==--


    def configure(self, parent):
        """ Show the configuration dialog """
        if self.cfgWin is None:
            self.cfgWin = gui.window.Window('FileExplorer.glade', 'vbox1', __name__, MOD_L10N, 370, 400)
            # Create the list of folders
            txtRdr  = gtk.CellRendererText()
            pixRdr  = gtk.CellRendererPixbuf()
            columns = ((None, [(txtRdr, TYPE_STRING)],                           0, False, False),
                       ('',   [(pixRdr, gtk.gdk.Pixbuf), (txtRdr, TYPE_STRING)], 2, False, True))

            self.cfgList = extListview.ExtListView(columns, sortable=False, useMarkup=True, canShowHideColumns=False)
            self.cfgList.set_headers_visible(False)
            self.cfgWin.getWidget('scrolledwindow1').add(self.cfgList)
            # Connect handlers
            self.cfgList.connect('key-press-event', self.onCfgKeyPressed)
            self.cfgList.get_selection().connect('changed', self.onCfgSelectionChanged)
            self.cfgWin.getWidget('btn-add').connect('clicked', self.onAddFolder)
            self.cfgWin.getWidget('btn-remove').connect('clicked', lambda btn: self.onRemoveSelectedFolder(self.cfgList))
            self.cfgWin.getWidget('btn-ok').connect('clicked', self.onBtnOk)
            self.cfgWin.getWidget('btn-rename').connect('clicked', self.onRenameFolder)
            self.cfgWin.getWidget('btn-cancel').connect('clicked', lambda btn: self.cfgWin.hide())
            self.cfgWin.getWidget('btn-help').connect('clicked', self.onHelp)

        if not self.cfgWin.isVisible():
            self.populateFolderList()
            self.cfgWin.getWidget('chk-hidden').set_active(self.showHiddenFiles)
            self.cfgWin.getWidget('chk-add-by-filename').set_active(self.addByFilename)
            self.cfgWin.getWidget('btn-ok').grab_focus()

        self.cfgWin.show()


    def populateFolderList(self):
        """ Populate the list of known folders """
        self.cfgList.replaceContent([(name, consts.icoBtnDir, '<b>%s</b>\n<small>%s</small>' % (cgi.escape(name), cgi.escape(path)))
                                     for name, path in sorted(self.folders.iteritems())])


    def onAddFolder(self, btn):
        """ Let the user add a new folder to the list """
        result = selectPath.SelectPath(MOD_L10N, self.cfgWin, self.folders.keys()).run()

        if result is not None:
            name, path = result
            self.folders[name] = path
            self.populateFolderList()
            modules.postMsg(consts.MSG_CMD_EXPLORER_ADD, {'modName': MOD_L10N, 'expName': name, 'icon': None, 'widget': self.scrolled})


    def onRemoveSelectedFolder(self, list):
        """ Remove the selected media folder """
        if list.getSelectedRowsCount() == 1:
            remark   = _('You will be able to add this root folder again later on if you wish so.')
            question = _('Remove the selected entry?')
        else:
            remark   = _('You will be able to add these root folders again later on if you wish so.')
            question = _('Remove all selected entries?')

        if gui.questionMsgBox(self.cfgWin, question, '%s %s' % (_('Your media files will not be deleted.'), remark)) == gtk.RESPONSE_YES:
            for row in self.cfgList.getSelectedRows():
                name = row[0]
                modules.postMsg(consts.MSG_CMD_EXPLORER_REMOVE, {'modName': MOD_L10N, 'expName': name})
                del self.folders[name]

                # Remove the tree, if any, from the scrolled window
                if self.currRoot == name:
                    self.scrolled.remove(self.trees[name][0])
                    self.currRoot = None

                # Remove the tree associated to this root folder, if any
                if name in self.tree:
                    del self.tree[name]

            self.cfgList.removeSelectedRows()


    def onRenameFolder(self, btn):
        """ Let the user rename a folder """
        name         = self.cfgList.getSelectedRows()[0][0]
        forbidden    = [rootName for rootName in self.folders if rootName != name]
        pathSelector = selectPath.SelectPath(MOD_L10N, self.cfgWin, forbidden)

        pathSelector.setPathSelectionEnabled(False)
        result = pathSelector.run(name, self.folders[name])

        if result is not None and result[0] != name:
            self.renameFolder(name, result[0])
            self.populateFolderList()


    def onCfgKeyPressed(self, list, event):
        """ Remove the selection if possible """
        if gtk.gdk.keyval_name(event.keyval) == 'Delete':
            self.onRemoveSelectedFolder(list)


    def onCfgSelectionChanged(self, selection):
        """ The selection has changed """
        self.cfgWin.getWidget('btn-remove').set_sensitive(selection.count_selected_rows() != 0)
        self.cfgWin.getWidget('btn-rename').set_sensitive(selection.count_selected_rows() == 1)


    def onBtnOk(self, btn):
        """ The user has clicked on the OK button """
        self.cfgWin.hide()
        self.setShowHiddenFiles(self.cfgWin.getWidget('chk-hidden').get_active())
        self.addByFilename = self.cfgWin.getWidget('chk-add-by-filename').get_active()


    def onHelp(self, btn):
        """ Display a small help message box """
        helpDlg = help.HelpDlg(MOD_L10N)
        helpDlg.addSection(_('Description'),
                           _('This module allows you to browse the files on your drives.'))
        helpDlg.addSection(_('Usage'),
                           _('At least one root folder must be added to browse your files. This folder then becomes the root of the '
                             'file explorer tree in the main window.'))
        helpDlg.show(self.cfgWin)
