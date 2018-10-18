# -*- coding: utf-8 -*-


class DTShellConstants(object):
    COMMANDS_REPO_OWNER = 'duckietown'
    COMMANDS_REPO_NAME = 'duckietown-shell-commands'
    COMMANDS_REPO_BRANCH = 'master'
    COMMANDS_REMOTE_URL = 'https://github.com/%s/%s' % (COMMANDS_REPO_OWNER, COMMANDS_REPO_NAME)
    ROOT = '~/.dt-shell/'
    ENV_COMMANDS = 'DTSHELL_COMMANDS'

    DT1_TOKEN_CONFIG_KEY = 'token_dt1'
    # DT1_TOKEN_ENV_VARIABLE = 'DUCKIETOWN_TOKEN'

    CONFIG_DOCKER_USERNAME = 'docker_username'
