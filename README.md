[![CircleCI](https://circleci.com/gh/duckietown/duckietown-shell.svg?style=shield)](https://circleci.com/gh/duckietown/duckietown-shell)
[![Docker Hub](https://img.shields.io/docker/pulls/duckietown/duckietown-shell.svg)](https://hub.docker.com/r/duckietown/duckietown-shell/)

# Duckietown Shell

*Duckietown Shell* is a pure Python, easily distributable (few dependencies) utility for Duckietown.

The idea is that most of the functionality is implemented as Docker containers, and `dt-shell` provides a nice interface for that, so that user should not type a very long `docker run` command line.

**Note: Duckietown Shell required Python 3.6 or higher.**

## Prerequisites

The duckietown shell has very minimal requirements.
Please use the links provided and follow the instructions for your OS

1. [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git/)
2. [Git LFS](https://git-lfs.github.com/) (for building and working with the docs only)
3. [Docker](https://docs.docker.com/get-docker/)

### Docker Prerequisites

**Note**: You need to add yourself to the `docker` group:

    $ sudo adduser `whoami` docker

**Important**: after you that, you must *log out and in* to have the group change take effect.

#### Docker on MacOS

By default Docker uses the OS X keychain to store credentials but this is not good.

Edit `~/.docker/config.json` and remove all references to a "osxkeychain".

Then run `docker login` again.

Then you should see an `auth` entry of the type:

    {
        "auths": {
            "https://index.docker.io/v1/": {
                "auth": "mXXXXXXXXXXXXXXXXXXXXXXXXXX"
            }
        },
    }

## Installing the Duckietown Shell

### Installation on Ubuntu 18.xx or 20.xx

**Note**: This OS is officially supported

#### Install using [pipx](https://pipx.pypa.io/stable/installation/)

Install `pipx`:

    $ sudo apt install -y pipx

Install the `duckietown-shell`:

    $ pipx install duckietown-shell

To upgrade to the latest version of `duckietown-sheel`:

    $ pipx upgrade duckietown-shell

#### Install using `pip`

Install `pip3`

    $ sudo apt install -y python3-pip

Install the `duckietown-shell` Python package:

    $ pip3 install --no-cache-dir --user -U duckietown-shell

#### Testing the Installation on Ubuntu

Typing

    $ which dts

should output something like: `/home/![user]/.local/bin/dts`

If nothing is output you may need to add `/home/![user]/.local/bin` to your shell path. You can do so by adding the line:

    `export PATH=$PATH:/root/.local/bin`

into your `~/.bashrc` file (if you use bash, otherwise the corresponding shell initialization file).

### Installation on Ubuntu 16.xx

The duckietown shell requires python 3.6 or higher, which is not standard on ubuntu16.
A currently working workaround is to install homebrew, by following instructions [here](https://docs.brew.sh/Homebrew-on-Linux).
Then, run :

    $ brew install python3
    $ python3.7 -m pip install --no-cache-dir --user -U duckietown-shell

Then, typing

    $ which dts

should output : `/home/linuxbrew/.linuxbrew/bin/dts`

### Duckietown Shell on MacOS X

#### Using `pipx` to install

Install `pipx`:

(see https://pipx.pypa.io/stable/installation/ for more details)

    $ brew install pipx
    $ pipx ensurepath
    $ sudo pipx ensurepath --global # optional to allow pipx actions in global scope. See "Global installation" section below.

Install the `duckietown-shell`:

    $ pipx install duckietown-shell

To upgrade to the latest version of `duckietown-sheel`:

    $ pipx upgrade duckietown-shell

#### Using `pip` to install

[Install `pip3`](https://evansdianga.com/install-pip-osx/).

Install the `duckietown-shell`:

**Note: Never use `sudo pip install` to install `duckietown-shell`.**

    $ pip3 install --no-cache-dir --user -U duckietown-shell

#### Testing the Installation

Typing

    $ which dts

should output the path to the `dts` executable. This path can vary based on your python setup.
If it is not found you may need to add something to your shell path.

### Installation in other operating systems

To install the shell, use:

    $ pip3 install --no-cache-dir --user -U duckietown-shell

The shell itself does not require any other dependency beside standard cross-platform Python libraries.

**Note: Never use `sudo pip3 install` to install `duckietown-shell`.**

### Installation on Docker (experimental)

Assuming that Docker is already installed, place the following
in your `~/.bashrc` or other initialization file for a shell:

    alias dts='docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock  -w $PWD -v $PWD:$PWD -v ~/.dt-shell:/root/.dt-shell -v ~/.docker:/root/.docker duckietown/duckietown-shell:v3 dts'

Some functionality might not be available.


## Testing Duckietown shell

At this point, try to enter the Duckietown shell by typing the command

    $ dts

If you get an error, delete the subfolder `commands` in the folder `~/.dt-shell`

    ~/.dt-shell$ rm -rf commands/

Then, try again

    $ dts

-----------------------

**You now have successfully installed the Duckietown Shell. If you know what you want to do with it go ahead. Below are some examples of things you can do with the Duckietown Shell**

## Compile one of the "Duckumentation"

To compile one of the books (e.g. docs-duckumentation but there are many others):

    $ git clone https://github.com/duckietown/docs-duckumentation.git
    $ cd docs-duckumentation
    $ git submodule init
    $ git submodule update
    $ dts docs build

There is an incremental build system. To clean and run from scratch:

    $ dts docs clean
    $ dts docs build


## Authenticate a Duckietown Token

Run the command `dts tok set` to set the Duckietown authentication token:

    $ dts tok set

Instructions will guide you and you will be prompted for the token.

If you already know the token, then you can use:

    $ dts tok set dt2-YOUR-TOKEN

### Verifying that a token is valid

To verify that a token is valid, you can use:

    $ dts tok verify dt2-TOKEN-TO-VERIFY

This exits with 0 if the token is valid, and writes on standard output the following json:

    {"uid": 3, "expiration": "2018-09-23"}

which means that the user is identified as uid 3 until the given expiration date.


-----------------------

## Duckiebot setup

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

## Uninstalling or resetting

In some cases, you might want to uninstall the `duckietown-shell`, or reset the configurations.

If you want to just uninstall the duckietown-shell python module, you could do:

    $ python3 -m pip uninstall duckietown-shell

If you also want to reset the settings, e.g. your Duckietown token, docker logins, version of the shell, etc, you would
also want to remove the `.duckietown/shell` folder in your home folder.
On Ubuntu/mac for example, this could be done with:

    $ rm -rf ~/.duckietown/shell

-----------------------

## Developing Duckietown Shell

Clone the Duckietown Shell repository

    $ git clone git@github.com:duckietown/duckietown-shell.git

### Install from Local Source

You can install Duckietown Shell from your local source

	$ cd duckietown-shell
    $ pipx install -e .

Note: using the `-e` option would install `dts` and link it directly to your source code. This means that any changes to the source code would reflect directly in the environment.

You can also use `pip` to install

    $ pip install -e .

### Running & Debugging from Visual Studio Code

To run the app in debug mode using Visual Studio Code, follow these steps:

1. Open the Debug view by clicking on the Debug icon in the Activity Bar on the side of the window.
2. Select the `dts` Launch configuration from the dropdown menu.
3. Click the green play button to start debugging.
4. Enter the arguments that you want to pass to the `dts` command, for example `profile list` -- this is the same as executing `dts profile list`.

This will launch the application in debug mode, allowing you to set breakpoints and step through the code.

### Developing Duckietown Shell Commands

**Note**: Duckietown Shell comes with a core set of commands used to manage the Duckietown Shell environment. All Duckietown specific commands come from the Duckietown Shell Commands repository - https://github.com/duckietown/duckietown-shell-commands

For Duckietown Shell Commands development, you need to tell `dts` where to find the command set.

Use the env variable to work on your local copy of the commands:

    export DTSHELL_COMMANDS=/path/to/my/duckietown-shell-commands

For additional information, see [devel](devel.md).

#### Debugging with Visual Studio Code

You can set the `DTSHELL_COMMANDS` variable via the `python.env` file located under `.vscode` directory.

To simplify development, you can symlink the `duckietown-shell-commands` directory/repository to be inside the `duckietown-shell` project:

```sh
# assuming that the duckietown-shell-commands repository has been cloned
# at the same level as the duckietown-shell repo
cd ~/duckietown-shell
ln -s $(realpath ../duckietown-shell-commands) ./
```

Note: don't forget to set your `DTSHELL_COMMANDS` environment variable by editing the `python.env` file.

This allows you to easily add breakpoints in the `duckietown-shell-commands` python files and run `dts` in debug mode.

