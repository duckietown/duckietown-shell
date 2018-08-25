# Duckietown Shell

*Duckietown Shell* is a pure Python, easily distributable (no dependencies) utility for Duckietown and AI-DO participants.

The idea is that most of the functionality is implemented as Docker containers, and `dt-shell` provides a nice interface for that, so that user should not type a very long `docker run` command line.


## Installation

To install the shell, use:

    $ sudo pip install --no-cache-dir -U duckietown-shell

That is, we should not require any other dependency beside standard cross-platform Python libraries.


### Ubuntu 18

    $ sudo apt install -y python-pip git
    $ sudo pip install --no-cache-dir -U duckietown-shell


### Troubleshooting


    Command dt not found, but can be installed with 
    
        sudo apt install ditrack
        
        
    
## Commands for Duckiebot setup

This starts the SD-card flashing procedure:

    $ dt init-sd-card

TODO: link to docs

##  Commands for AI-DO 

### (TODO) AI-DO templates download

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

## Commands for duckumentation

    $ dt docs build
    $ dt docs clean

## (TODO) Commands for logs

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



## Advanced

### Docker

To launch the Duckietown Shell in Docker, run the following command:

    $ docker run -it duckietown/duckietown-shell
    
Note: the Duckietown Shell is supposed to be run natively from the host.

### Local commands development

Use the env variable to work on your local copy of the commands:

    export DTSHELL_COMMANDS=/path/to/my/duckietown-shell-commands
 
   
