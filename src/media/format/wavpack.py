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

from mutagen.wavpack       import WavPack
from media.track.fileTrack import FileTrack


def getTrack(file):
    """ Return a Track created from a WavPack file """
    track  = FileTrack(file)
    wvFile = WavPack(file)

    track.setLength(int(round(wvFile.info.length)))

    try:    track.setTitle(str(wvFile['Title'][0]))
    except: pass

    try:    track.setAlbum(str(wvFile['Album'][0]))
    except: pass

    try:    track.setArtist(str(wvFile['Artist'][0]))
    except: pass

    try:    track.setAlbumArtist(str(wvFile['Album Artist'][0]))
    except: pass

    try:    track.setGenre(str(wvFile['genre'][0]))
    except: pass

    try:    track.setNumber(int(str(wvFile['Track'][0]).split('/')[0]))     # Track format may be 01/08, 02/08...
    except: pass

    try:    track.setDiscNumber(int(str(wvFile['Disc'][0]).split('/')[0]))  # Disc number format may be 01/02, 02/02...
    except: pass

    try:    track.setDate(int(wvFile['Year'][0]))
    except: pass

    return track
