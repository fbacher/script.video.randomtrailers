Welcome to the Kodi-script.video.randomtrailers wiki!

Mission: To resurrect the orphaned and non-functioning Kodi random trailers
screensaver and script.

Status:

Complete rewrite. A lot more function, but bigger. Beta. Fully functional,
but limited testing with Kodi 19 using Python 3.8 & 3.9.

See RELEASE_NOTES.txt for information not contained here.

Major accomplishments:

    * Feature complete
    * Multi-threaded to speed up discovery, improve randomness and eliminate
      wait to download information before each play of remote content

Among the features:

    * Gets trailers from the library, TMDb, TFH and local trailers folder
    * Falls back to TMDb for missing trailers from local database
    * Falls back to TMDb for missing local and TFH movie details

    * One addon, with three extension points:
        1- A trailer discovery module that performs the hard work of finding
           and caching the trailers. Runs as a daemon.
        2- A Frontend is the user facing app. It is used for both screensaver
           and manual launch.
        3- A screensaver service. This thin piece of code gets launched by
           Kodi's screensaver function. It then starts up the frontend.

    * Supports a local cache for trailers and information downloaded from
      remote sites
    * Supports Normalization of audio, mostly to help ghastly trailers/clips
      originating from youtube
    * Filter by Genre, Certification, year, rating, popularity, etc. for
      local, TMDb and TFH
    * Can configure various cache attributes: max size, max number of
      files, max % of disk, delete old files.
    * Plugin runs stand alone or as a screensaver
    * Back-end is a separate long-running service, reducing startup time
      and high startup cost
    * User ability to add current trailer to a playlist mostly to flag
      movies that they would like to watch, or note for any reason
    * Internationalized (limited testing). All messages use translation
      system. Country code and language used in remote movie queries
    * Genre information is loaded from .xml files allowing customization
    * Certification/Rating information is loaded from .xml files to allow
      different rules and names by country. (Kodi appears to have some
      limitations in this area: ratings do not include country info.)

    Support for Text to Speech plugin (under development)
