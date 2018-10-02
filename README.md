# Duckietown Shell

*Duckietown Shell* is a pure Python, easily distributable (few dependencies) utility for Duckietown.

The idea is that most of the functionality is implemented as Docker containers, and `dt-shell` provides a nice interface for that, so that user should not type a very long `docker run` command line.

## Prerequisites

You must be using `pip` with Python 2.x to use Duckietown Shell.

Check the output of this command:

    $ pip --version # Should return something like: pip 18.0 from ...python2.7/site-packages/pip (python 2.7)

If it says "2.7", you are golden and can skip down to "installation".

Otherwise make a virtual environment as suggested below.


### Python 2 virtual environment (necessary if Python 3 is the default)

Install `virtualenv`:

    $ pip install virtualenv
    
Then create a new virtual environment, `dts`:

    $ virtualenv -p `which python2` dts
    
Then activate the `dts` environment:

    $ source dts/bin/activate
    (dts) $ 

Now, you now should be ready to install `duckietown-shell`. To deactivate `dts` later, run `deactivate`.

## Installation

These installation steps make sure that you have a minimal "sane" environment, which includes:

1. Git and Git LFS;
2. Docker;
3. The Duckietown Shell.

### Installation on Ubuntu 18.xx

Installs pip, git, git-lfs, docker, duckietown-shell:

    $ sudo apt install -y python-pip git git-lfs
    
    $ sudo apt install -y docker.io
    $ sudo adduser `whoami` docker
    
    $ pip2 install --no-cache-dir -U duckietown-shell
    
Note: you need to *log in and out* to have the group change take effect.

**Note: Never use `sudo pip install` to install `duckietown-shell`.**

### Installation on Ubuntu 16.xx

Installs pip, git, git-lfs, docker, duckietown-shell:

    $ sudo apt-get install software-properties-common  curl
    $ sudo add-apt-repository ppa:git-core/ppa
    $ curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
    $ sudo apt-get install  -y python-pip git git-lfs 
    
    $ curl -fsSL https://get.docker.com | sudo bash
    $ sudo usermod -aG docker `whoami` 
    
    $ pip2 install --no-cache-dir -U duckietown-shell
    
Note: you need to *log in and out* to have the group change take effect.

**Note: Never use `sudo pip install` to install `duckietown-shell`.**

### Installation in other operating systems

You will need to find the instructions for git, git-lfs, docker.

To install the shell, use:

    $ pip2 install --no-cache-dir -U duckietown-shell

The shell itself does not require any other dependency beside standard cross-platform Python libraries.

**Note: Never use `sudo pip install` to install `duckietown-shell`.**
 
-----------------------
        

## Commands for compiling the Duckumentation

To compile one of the books:

    $ git clone https://github.com/duckietown/docs-duckumentation.git
    $ cd docs-duckumentation
    $ git submodule init
    $ git submodule update
    $ dts docs build

There is an incremental build system. To clean and run from scratch:

    $ dts docs clean
    $ dts docs build

TODO: link to docs

    

-----------------------
        

## Duckietown Authentication Token setup

Run the command `dts tok set` to set the Duckietown authentication token:

    $ dts tok set  

Instructions will guide you and you will be prompted for the token.

If you already know the token, then you can use:

    $ dts tok set dt1-YOUR-TOKEN
    
### Verifying that a token is valid

To verify that a token is valid, you can use:

    $ dts tok verify dt1-TOKEN-TO-VERIFY
    
This exits with 0 if the token is valid, and writes on standard output the following json:

    {"uid": 3, "expiration": "2018-09-23"}
    
which means that the user is identified as uid 3 until the given expiration date.
 

-----------------------

## Commands for Duckiebot setup

### Command for flashing SD card

This command will install DuckieOS on the SD-card:

    $ dts init_sd_card

-----------------------

### Command for starting ROS GUIs

This command will start the ROS GUI container:

    $ dts start_gui_tools <DUCKIEBOT_NAME_GOES_HERE>

-----------------------

### Command for calibrating the Duckiebot

This command will run the Duckiebot calibration procedure:

    $ dts calibrate_duckiebot <DUCKIEBOT_NAME_GOES_HERE>

-----------------------

##  Commands for AI-DO 1 

### (TODO) AI-DO templates download

*Not implemented yet*

The subcommand `get-template` downloads the submission templates.

Downloads the current template:

    $ dts aido1 get-template TASK-LANG
    checking out repository...

Without arguments, the program writes a list of available templates.


### (TODO) AI-DO submissions

*Not implemented yet*

The command `submit` submits the entry in the current directory:

    $ dts aido1 submit

### (TODO )Submissions status

The command `status` displays the status of the submitted entries:

    $ dts aido1 status
    jobname  task  docker hash  status
    jobname  task  docker hash  status
    ...

-----------------------


## (TODO) Commands for logs

Wrappers are provided for the [EasyLogs commands][easy_logs].

    $ dts logs summary
    $ dts logs download
    $ dts logs copy
    $ dts logs details
    $ dts logs make-thumbnails
    $ dts logs make-video

[easy_logs]: http://docs.duckietown.org/software_devel/out/easy_logs.html

### Summary, details

Queries the list of logs that satisfy a query:

    $ dts logs summary "vehicle:yaf,length:>120s"

Show more details about one log:

    $ dts logs details 20171124170042_yaf

### Download, copy

Downloads logs to the local computer:

    $ dts logs download 20171124170042_yaf

Copies the logs to a specific directory:

    $ dts logs copy -o ![output dir] 20171124170042_yaf
    Creating ![output dir]/20171124170042_yaf.bag

### Creating thumbnails

    $ dts logs make-thumbnails 20171124170042_yaf

### Creating videos:

Create a video of the camera data:

    $ dts logs make-videos 20171124170042_yaf

### Advanced configuration

By default, Duckietown Shell uses the folder `~/dt-data` for storing log data and other cache data.

Alternatively, you can use the `--dt-data` argument to choose a different folder:

    $ dts logs --dt-data ![dir] ![command]

Alternatively, the directory can be specified using the environment variable `DT_DATA`.

    $ DT_DATA=/tmp/data dt logs summary

-----------------------

## Information for Duckietown Shell developers

### Docker

To launch the Duckietown Shell in Docker, run the following command:

    $ docker run -it duckietown/duckietown-shell
    
Note: the Duckietown Shell is supposed to be run natively from the host.

### Local commands development

Use the env variable to work on your local copy of the commands:

    export DTSHELL_COMMANDS=/path/to/my/duckietown-shell-commands
 
   
