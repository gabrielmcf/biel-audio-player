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

import pygst
pygst.require('0.10')
import gst


class AudioPlayer:

    def __init__(self, callbackEnded, usePlaybin2=False):
        """ Constructor """
        if usePlaybin2:
            self.player = gst.element_factory_make('playbin2', 'player')
            self.player.connect('about-to-finish', self.__onAboutToFinish)
        else:
            self.player = gst.element_factory_make('playbin', 'player')

        self.nextURI       = None
        self.equalizer     = None
        self.replaygain    = None
        self.callbackEnded = callbackEnded

        # No video
        self.player.set_property('video-sink', gst.element_factory_make('fakesink', 'fakesink'))

        # Change the audio sink to our own bin, so that an equalizer/replay gain element can be added later on if needed
        self.audiobin  = gst.Bin('audiobin')
        self.audiosink = gst.element_factory_make('autoaudiosink', 'audiosink')

        self.audiobin.add(self.audiosink)
        self.audiobin.add_pad(gst.GhostPad('sink', self.audiosink.get_pad('sink')))
        self.player.set_property('audio-sink', self.audiobin)

        # Monitor messages generated by the player
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.__onGstMessage)


    def __onAboutToFinish(self, isLast):
        """ Feed the next URI if we have one """
        if self.nextURI is not None:
            self.player.set_property('uri', self.nextURI)
            self.nextURI = None
            self.callbackEnded(False)


    def __onGstMessage(self, bus, msg):
        """ A new message generated by the player """
        if   msg.type == gst.MESSAGE_EOS:   self.callbackEnded(False)
        elif msg.type == gst.MESSAGE_ERROR: self.callbackEnded(True)

        return True


    def setNextURI(self, uri):
        """ Set the next URI """
        self.nextURI = uri.replace('#', '%23')


    def clearNextURI(self):
        """ Clear the next URI """
        self.nextURI = None


    def setVolume(self, level):
        """ Set the volume to the given level (0 <= level <= 1) """
        if level < 0:   level = 0
        elif level > 1: level = 1

        self.player.set_property('volume', level)


    def __saveRestoreState(self, func):
        """  """
        savedState = self.player.get_state()[1]
        self.player.set_state(gst.STATE_NULL)
        func()
        self.player.set_state(savedState)


    def __enableEqualizer(self):
        """ Add an equalizer to the audio chain """
        self.equalizer = gst.element_factory_make('equalizer-10bands', 'equalizer')
        self.audiobin.add(self.equalizer)

        if self.replaygain is None:
            self.audiobin.get_pad('sink').set_target(self.equalizer.get_pad('sink'))
        else:
            self.replaygain.unlink(self.audiosink)
            self.replaygain.link(self.equalizer)

        self.equalizer.link(self.audiosink)


    def __enableReplayGain(self):
        """ Add/Enable a replay gain element """
        if self.replaygain is None:
            self.replaygain = gst.element_factory_make('rgvolume', 'replaygain')

        self.audiobin.add(self.replaygain)
        self.audiobin.get_pad('sink').set_target(self.replaygain.get_pad('sink'))

        if self.equalizer is None: self.replaygain.link(self.audiosink)
        else:                      self.replaygain.link(self.equalizer)


    def __disableReplayGain(self):
        """ Disable the replay gain element, if any """
        if self.replaygain is not None:
            if self.equalizer is None: self.audiobin.get_pad('sink').set_target(self.audiosink.get_pad('sink'))
            else:                      self.audiobin.get_pad('sink').set_target(self.equalizer.get_pad('sink'))

            self.audiobin.remove(self.replaygain)


    def enableEqualizer(self):
        """ Add an equalizer to the audio chain """
        self.__saveRestoreState(self.__enableEqualizer)


    def enableReplayGain(self):
        """ Add/Enable a replay gain element """
        self.__saveRestoreState(self.__enableReplayGain)


    def disableReplayGain(self):
        """ Disable the replay gain element, if any """
        self.__saveRestoreState(self.__disableReplayGain)


    def setEqualizerLvls(self, lvls):
        """ Set the level of the 10-bands of the equalizer (levels must be a list/tuple with 10 values lying between -24 and +12) """
        if len(lvls) == 10 and self.equalizer is not None:
            self.equalizer.set_property('band0', lvls[0])
            self.equalizer.set_property('band1', lvls[1])
            self.equalizer.set_property('band2', lvls[2])
            self.equalizer.set_property('band3', lvls[3])
            self.equalizer.set_property('band4', lvls[4])
            self.equalizer.set_property('band5', lvls[5])
            self.equalizer.set_property('band6', lvls[6])
            self.equalizer.set_property('band7', lvls[7])
            self.equalizer.set_property('band8', lvls[8])
            self.equalizer.set_property('band9', lvls[9])


    def isPaused(self):
        """ Return whether the player is paused """
        return self.player.get_state()[1] == gst.STATE_PAUSED


    def isPlaying(self):
        """ Return whether the player is paused """
        return self.player.get_state()[1] == gst.STATE_PLAYING


    def setURI(self, uri):
        """ Play the given URI """
        self.player.set_property('uri', uri.replace('#', '%23'))


    def play(self):
        """ Play """
        self.player.set_state(gst.STATE_PLAYING)


    def pause(self):
        """ Pause """
        self.player.set_state(gst.STATE_PAUSED)


    def stop(self):
        """ Stop playing """
        self.player.set_state(gst.STATE_NULL)


    def seek(self, where):
        """ Jump to the given location """
        self.player.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, where)


    def getPosition(self):
        """ Return the current position """
        return self.player.query_position(gst.FORMAT_TIME)[0]


    def getDuration(self):
        """ Return the duration of the current stream """
        return self.player.query_duration(gst.FORMAT_TIME)[0]
