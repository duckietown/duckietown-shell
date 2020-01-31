[![CircleCI](https://circleci.com/gh/duckietown/duckietown-shell.svg?style=shield)](https://circleci.com/gh/duckietown/duckietown-shell) 
[![Docker Hub](https://img.shields.io/docker/pulls/duckietown/duckietown-shell.svg)](https://hub.docker.com/r/duckietown/duckietown-shell/)

# Duckietown Shell

*Duckietown Shell* is a pure Python, easily distributable (few dependencies) utility for Duckietown.

The idea is that most of the functionality is implemented as Docker containers, and `dt-shell` provides a nice interface for that, so that user should not type very long `docker run` commands in the command line.

For a description of the commands see [the duckietown-shell-commands README](https://github.com/duckietown/duckietown-shell-commands/blob/daffy/README.md) 


 
## General instructions

Regardless of operating system you will need to install the following:

1. Git and Git LFS;
2. Docker;
3. The Duckietown Shell.

**Note: Duckietown Shell required Python 3.6 or higher.**

**Note: Never use root (e.g. `sudo` to install `duckietown-shell`). It will make for problems later**

What is below guides you through the process for specific Operating Systems.

 - [Ubuntu 18](#ubuntu-18xx)
 - [Ubuntu 16](#ubuntu-16xx)
 - [Mac OSX](#mac-osx)
 - [All other operating systems](#other-operating-systems)
 - [Inside a docker image](#inside-docker-experimental)
 

Once you have completed the installation, you can test it by trying to enter the Duckietown shell by typing the command

    $ dts

which should give you an output that is something like: 

```INFO:dts:duckietown-shell ![SHELL_VERSION]

dts :  Problems with a command?
    :  
    :      Report here: https://github.com/duckietown/duckietown-shell-commands/issues
    :  
    :      Troubleshooting:
    :  
    :      - If some commands update fail, delete ~/.dt-shell/commands
    :  
    :      - To reset the shell to "factory settings", delete ~/.dt-shell
    :  
    :        (Note: you will have to re-configure.)
INFO:dts:Commands version: ![SHELL_VERSION]
INFO:dts:looking at ![HOME]/.dt-shell/commands-multi/![SHELL_VERSION]

%%%%%% you may or may not see the following

dts :  An updated version of the commands is available.
    :  
    :  Attempting auto-update.

dts :  Updating commands...

%%%%%%

dts :  OK
INFO:dts:duckietown-shell-commands ![SHELL_COMMANDS_VERSION]
INFO:duckietown-challenges:duckietown-challenges ![CHALLENGES_VERSION]
INFO:zj:zuper-ipce ![ZUPER_IPCE_VERSION]
INFO:zuper-typing:zuper-typing ![ZUPER_TYPING_VERSION]
INFO:zuper-commons:zuper-commons ![ZUPER_COMMONS_VERSION]
Welcome to the Duckietown Shell (![SHELL_VERSION]).

Type "help" or "?" to list commands.


(Cmd)
```

If you get a message that says that you should update the shell, you can do so by executing whichever `pip` command you used to install the shell and adding the `--upgrade` flag. 

_Pro Tip_: add an alias to your `~/.bashrc` file when you install the shell to do the upgrade. E.g. 

    alias upgrade_shell='pip3 install --no-cache-dir --user -U --upgrade duckietown-shell'

Once you are inside the shell you can execute any of the [duckietown shell commands](https://github.com/duckietown/duckietown-shell-commands).

*Note*: you don't have to enter the shell to execute a command, you can do it all in one line with

    $ dts ![command]

You can also see the commands that are available with the special command `commands`. It is possible that some commands are not installed by default in which case they will be listed as "Installable" and you can install them with the shell command `install`. E.g.:

    $ (Cmd) install docs


### Ubuntu 18.xx 

Installs `pip3`, `git`, `git-lfs`:

    $ sudo apt install -y python3-pip git git-lfs
    
Installs `docker`: (Also could refer to: https://docs.docker.com/install/linux/docker-ce/ubuntu/)

    $ sudo apt install -y docker.io
    $ sudo adduser `whoami` docker

Installs `duckietown-shell`:



    $ pip3 install --no-cache-dir --user -U duckietown-shell

Note: you need to *log in and out* to have the group change take effect.

Then, typing 

    $ which dts
    
should output something like: `/home/user/.local/bin/dts`

### Ubuntu 16.xx

**Note: Ubuntu 16 is no longer officially supported. We require a python version >= 3.6 which is not natively distributed with Ubuntu 16. It is possible to make it work, but you will have to upgrade the python version manually**

A currently working workaround for the above is to install homebrew, by following instructions [here]( https://docs.brew.sh/Homebrew-on-Linux)

Then, run :

    $ brew install python3
    $ python3.7 -m pip install --no-cache-dir --user -U duckietown-shell


For the other dependencies, run:

    $ sudo apt install -y git git-lfs
    
    $ sudo apt install -y docker.io
    $ sudo adduser `whoami` docker



Finally, test the setup by doing:

    $ which dts

and if you did the homebrew python instruction you should see: `/home/linuxbrew/.linuxbrew/bin/dts`


### Mac OSX

#### Make sure you have a version of python3 >= 3.6:

    $ python3 --version
    
If not find instructions [here](https://www.python.org/). 

#### Make sure you have pip3:

    $ which pip3 
    
Should output some path to the executable (e.g., `/usr/local/bin/pip3`). If nothing is printed then the following instructions take from [here] should work:

    $ curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $ python3 get-pip.py

#### Install git and git-lfs

Check if you have git installed with:

    $ git --version

You should see the path get printed out. If not, install git with 

    $ brew install git

Finally, follow the instructions [here](https://github.com/git-lfs/git-lfs/wiki/Installation) to install `git-lfs`. 

#### Install docker

Follow the instructions [here](https://docs.docker.com/docker-for-mac/install/) to install docker. 

#### Install the duckietown shell

If you followed the steps above, to install the shell, use:

    $ pip3 install --no-cache-dir --user -U duckietown-shell

The shell itself does not require any other dependency beside standard cross-platform Python libraries.

You will have to add the path to the binary to your PATH variable. 
This can be done with 

    $ echo "export PATH=$PATH:$HOME/Library/Python/3.7/bin" >> ~/.bash_profile

and then reopen your terminal for the changes to take effect.



### Other operating systems

You will need to find the instructions for installing pip, git, git-lfs, docker, and python3 (version at least 3.6) for your specific operating system on your own.

To install the shell, use:

    $ pip3 install --no-cache-dir --user -U duckietown-shell

The shell itself does not require any other dependency beside standard cross-platform Python libraries.



### Inside Docker (experimental)

Assuming that Docker is already installed, place the following
in your `~/.bashrc` or other initialization file for a shell:

    alias dts='docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock  -w $PWD -v $PWD:$PWD -v ~/.dt-shell:/root/.dt-shell -v ~/.docker:/root/.docker duckietown/duckietown-shell:v3 dts'

Some functionality might not be available.


#### Docker on Mac OSX

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








