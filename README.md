# Duckietown Shell

*Duckietown Shell* is a pure Python, easily distributable (no dependencies) utility for Duckietown and AI-DO participants.

The idea is that most of the functionality is implemented as Docker containers, and `dt-shell` provides a nice interface for that, so that user should not type a very long `docker run` command line.

The installation should just be, on any platform:

    $ pip install --no-cache-dir --user -U duckietown-shell
    $ dt help

That is, we should not require any other dependency beside standard cross-platform Python libraries.


## Commands for Duckiebot setup

This starts the SD-card flashing procedure:

    $ dt init-sd-card

TODO: to implement


##  Commands for AI-DO

### AI-DO registration

You can register for the AI-DO via command line using:

    $ dt aido18 register
    First: ...
    Last: ...
    Email: ...
    Password: ...

This also creates a remote account on the website.

### AI-DO templates download

The subcommand `get-template` downloads the submission templates.

Downloads the current template:

    $ dt aido18 get-template TASK-LANG
    checking out repository...

Without arguments, the program writes a list of available templates.


### AI-DO login

The command `login` authenticates the AI-DO account. It is needed
before running one of the next commands

    $ dt aido18 login
    Username: ...
    Password: ...


### AI-DO submissions

The command `submit` submits the entry in the current directory:

    $ dt aido18 submit

### Submissions status

The command `status` displays the status of the submitted entries:

    $ dt aido18 status
    jobname  task  docker hash  status
    jobname  task  docker hash  status
    ...


## Commands for logs

Wrappers are provided for the [EasyLogs commands][easy_logs].

    $ dt logs summary
    $ dt logs download
    $ dt logs copy
    $ dt logs details
    $ dt logs make-thumbnails
    $ dt logs make-video

[easy_logs]: http://docs.duckietown.org/software_devel/out/easy_logs.html

### Summary, details

Queries the list of logs that satisfy a query:

    $ dt logs summary "vehicle:yaf,length:>120s"

Show more details about one log:

    $ dt logs details 20171124170042_yaf

### Download, copy

Downloads logs to the local computer:

    $ dt logs download 20171124170042_yaf

Copies the logs to a specific directory:

    $ dt logs copy -o ![output dir] 20171124170042_yaf
    Creating ![output dir]/20171124170042_yaf.bag

### Creating thumbnails

    $ dt logs make-thumbnails 20171124170042_yaf

### Creating videos:

Create a video of the camera data:

    $ dt logs make-videos 20171124170042_yaf

### Advanced configuration

By default, Duckietown Shell uses the folder `~/dt-data` for storing log data and other cache data.

Alternatively, you can use the `--dt-data` argument to choose a different folder:

    $ dt logs --dt-data ![dir] ![command]

Alternatively, the directory can be specified using the environment variable `DT_DATA`.

    $ DT_DATA=/tmp/data dt logs summary
