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

import gtk, gui, modules, os.path

from media     import track
from tools     import consts, prefs
from gettext   import gettext as _
from tools.log import logger

MOD_INFO = ('Desktop Notification', _('Desktop Notification'), _('Display a desktop notification on track change'), ['pynotify'], False, True)
MOD_L10N = MOD_INFO[modules.MODINFO_L10N]

# Default preferences
PREFS_DEFAULT_BODY       = 'by {artist}\nfrom {album}\n\nTrack {playlist_pos} out of {playlist_len}'
PREFS_DEFAULT_TITLE      = '{title}  [{duration_str}]'
PREFS_DEFAULT_TIMEOUT    = 10
PREFS_DEFAULT_SKIP_TRACK = False


class DesktopNotification(modules.ThreadedModule):

    def __init__(self):
        """ Constructor """
        modules.ThreadedModule.__init__(self, (consts.MSG_EVT_APP_STARTED, consts.MSG_EVT_MOD_LOADED,   consts.MSG_EVT_NEW_TRACK,
                                               consts.MSG_EVT_APP_QUIT,    consts.MSG_EVT_MOD_UNLOADED, consts.MSG_EVT_STOPPED,
                                               consts.MSG_EVT_TRACK_MOVED))


    def initPynotify(self):
        """ Return whether pynotify could be initialized, must be called by the GTK loop """
        import pynotify

        return pynotify.init(consts.appNameShort)


    def onModLoaded(self):
        """ The module has been loaded """
        self.icon        = gtk.STOCK_DIALOG_INFO
        self.notif       = None
        self.cfgWin      = None
        self.hasNext     = False
        self.initialized = False

        if self.gtkExecute(self.initPynotify): self.initialized = True
        else:                                  logger.error('[%s] Initialization failed' % MOD_INFO[modules.MODINFO_NAME])


    def showNotification(self, track):
        """ Show the notification based on the given track """
        body  = track.formatHTMLSafe(prefs.get(__name__, 'body',  PREFS_DEFAULT_BODY))
        title = track.format(prefs.get(__name__, 'title', PREFS_DEFAULT_TITLE))

        # Make sure the notification exists
        if self.notif is None:
            import pynotify

            img = os.path.join(consts.dirPix, 'decibel-audio-player-64.png')
            if os.path.isfile(img):
                self.icon = 'file://' + img

            self.notif = pynotify.Notification(title, body, self.icon)
            self.notif.set_urgency(pynotify.URGENCY_LOW)
            self.notif.set_timeout(prefs.get(__name__, 'timeout', PREFS_DEFAULT_TIMEOUT) * 1000)

            if prefs.get(__name__, 'skip-track', PREFS_DEFAULT_SKIP_TRACK):
                self.notif.add_action('stop', _('Skip track'), self.onSkipTrack)

        self.notif.update(title, body, self.icon)
        self.notif.show()


    def onSkipTrack(self, notification, action):
        """ The user wants to skip the current track """
        if self.hasNext: modules.postMsg(consts.MSG_CMD_NEXT)
        else:            modules.postMsg(consts.MSG_CMD_STOP)


    # --== Message handler ==--


    def handleMsg(self, msg, params):
        """ Handle messages sent to this module """
        if msg == consts.MSG_EVT_NEW_TRACK and self.initialized:
            self.showNotification(params['track'])
        elif msg in (consts.MSG_EVT_APP_STARTED, consts.MSG_EVT_MOD_LOADED):
            self.onModLoaded()
        elif msg in (consts.MSG_EVT_APP_QUIT, consts.MSG_EVT_MOD_UNLOADED, consts.MSG_EVT_STOPPED) and self.notif is not None:
            self.notif.close()
        elif msg == consts.MSG_EVT_TRACK_MOVED:
            self.hasNext = params['hasNext']


    # --== Configuration ==--


    def configure(self, parent):
        """ Show the configuration window """
        if self.cfgWin is None:
            import pynotify

            self.cfgWin = gui.window.Window('DesktopNotification.glade', 'vbox1', __name__, MOD_L10N, 355, 345)
            self.cfgWin.getWidget('btn-ok').connect('clicked', self.onBtnOk)
            self.cfgWin.getWidget('btn-help').connect('clicked', self.onBtnHelp)
            self.cfgWin.getWidget('btn-cancel').connect('clicked', lambda btn: self.cfgWin.hide())

            if 'actions' not in pynotify.get_server_caps():
                self.cfgWin.getWidget('chk-skipTrack').set_sensitive(False)

        if not self.cfgWin.isVisible():
            self.cfgWin.getWidget('txt-title').set_text(prefs.get(__name__, 'title', PREFS_DEFAULT_TITLE))
            self.cfgWin.getWidget('spn-duration').set_value(prefs.get(__name__, 'timeout', PREFS_DEFAULT_TIMEOUT))
            self.cfgWin.getWidget('txt-body').get_buffer().set_text(prefs.get(__name__, 'body', PREFS_DEFAULT_BODY))
            self.cfgWin.getWidget('chk-skipTrack').set_active(prefs.get(__name__, 'skip-track', PREFS_DEFAULT_SKIP_TRACK))
            self.cfgWin.getWidget('btn-ok').grab_focus()

        self.cfgWin.show()


    def onBtnOk(self, btn):
        """ Save new preferences """
        # Skipping tracks
        newSkipTrack = self.cfgWin.getWidget('chk-skipTrack').get_active()
        oldSkipTrack = prefs.get(__name__, 'skip-track', PREFS_DEFAULT_SKIP_TRACK)

        prefs.set(__name__, 'skip-track', newSkipTrack)

        if oldSkipTrack != newSkipTrack and self.notif is not None:
            if newSkipTrack: self.notif.add_action('stop', _('Skip track'), self.onSkipTrack)
            else:            self.notif.clear_actions()

        # Timeout
        newTimeout = int(self.cfgWin.getWidget('spn-duration').get_value())
        oldTimeout = prefs.get(__name__, 'timeout', PREFS_DEFAULT_TIMEOUT)

        prefs.set(__name__, 'timeout', newTimeout)

        if oldTimeout != newTimeout and self.notif is not None:
            self.notif.set_timeout(newTimeout * 1000)

        # Other preferences
        prefs.set(__name__, 'title', self.cfgWin.getWidget('txt-title').get_text())
        (start, end) = self.cfgWin.getWidget('txt-body').get_buffer().get_bounds()
        prefs.set(__name__, 'body', self.cfgWin.getWidget('txt-body').get_buffer().get_text(start, end))
        self.cfgWin.hide()


    def onBtnHelp(self, btn):
        """ Display a small help message box """
        helpDlg = gui.help.HelpDlg(MOD_L10N)
        helpDlg.addSection(_('Description'),
                           _('This module displays a small popup window on your desktop when a new track starts.'))
        helpDlg.addSection(_('Customizing the Notification'),
                           _('You can change the title and the body of the notification to any text you want. Before displaying '
                             'the popup window, fields of the form {field} are replaced by their corresponding value. '
                             'Available fields are:\n\n') + track.getFormatSpecialFields(False))
        helpDlg.addSection(_('Markup'),
                           _('You can use the Pango markup language to format the text. More information on that language is '
                             'available on the following web page:') + '\n\nhttp://www.pygtk.org/pygtk2reference/pango-markup-language.html')
        helpDlg.show(self.cfgWin)
