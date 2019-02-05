# monitors onScreensaverActivated event and checks guisettings.xml for plugin.video.randomtrailers.
# if found it will launch plugin.video.randomtrailers which will show trailers.
# this gets around Kodi killing a screensaver 5 seconds after
# onScreensaverDeactivate

import xbmc
import os


def isTrailerScreensaver():
    pguisettings = xbmc.translatePath(os.path.join(
        'special://userdata', 'guisettings.xml')).decode('utf-8')
    xbmc.log(pguisettings)
    name = '<mode>script.video.randomtrailers</mode>'
    if name in file(pguisettings, "r").read():
        xbmc.log('found script.video.randomtrailers in guisettings.html')
        return True
    else:
        xbmc.log('did not find script.video.randomtrailers in guisettings.html')
        return False


class MyMonitor(xbmc.Monitor):

    def __init__(self):
        pass

    def onScreensaverActivated(self):
        if isTrailerScreensaver():
            xbmc.executebuiltin(
                'xbmc.RunScript("script.video.randomtrailers","no_genre")')


m = MyMonitor()
while (not xbmc.Monitor().abortRequested()):
    xbmc.sleep(1000)
xbmc.Player().stop
del m
