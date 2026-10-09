
# Information for Duckietown Shell developers

### Docker

To launch the Duckietown Shell in Docker, run the following command:

    $ docker run -it duckietown/duckietown-shell
    
Note: the Duckietown Shell is supposed to be run natively from the host.

### Local commands development

Use the env variable to work on your local copy of the commands:

    export DTSHELL_COMMANDS=/path/to/my/duckietown-shell-commands
 
### Use local challenge server

Use the env variable `DTSERVER` to work on a local server:

    export DTSERVER=http://localhost:6544/
 

### Plan authorization for `ente`

The `ente` distribution, including its staging variant, requires the free
"Independent User" plan or an active "Institutional User" plan. The "Instructor"
plan is an add-on to the "Institutional User" plan and does not grant `ente`
access by itself. Staff and superusers are exempt from both the plan requirement
and the computer limit.
The `daffy` distribution and its staging variant do not require a plan. Core token, profile, and command
management commands remain available, and ordinary token generation is unchanged.

DTS obtains a signed, non-renewable authorization for `ente` from
`/api/v1/auth/token/ente/` and caches it per profile, identity token, and Hub.
The grant is bound to the user, Hub, and registered computer. Its signed expiration
is the earlier of 24 hours and any recorded expiration of the plan granting access.
Redeemed seats for the "Institutional User" plan use their parent plan's expiration;
the "Instructor" plan does not extend it. Qualifying plan flags without a recorded
validity period, including enrollment in the free "Independent User" plan, retain daily authorization
with no recorded plan expiration.
The cached grant is checked locally and refreshed on demand after at most 24 hours,
or earlier if its signed expiration is reached. Without a valid cached grant,
an unavailable Hub blocks `ente` commands but does not block `daffy` commands.

Each non-staff account can register one DTS computer. Identity-token or cache
copies do not authorize a different computer in the supported client. The
fingerprint hashes the Linux machine ID, macOS platform UUID, or Windows
MachineGuid; VMs, separate OS installations, and reinstalls may have different
identities. No raw machine ID is sent to Hub.

```shell
dts subscription status
dts subscription transfer
```

Status distinguishes **Account plans** (all plans listed on the account, including
add-ons) from **Plan granting 'ente' access** (the qualifying "Independent User"
plan or "Institutional User" plan). The **Plan requirement for 'ente'** shows
whether the account meets that requirement or is exempt; it is not a promise that
the current computer can obtain a grant during a pending transfer.
It also shows any recorded plan expiration, the registered computer, the latest
expiry among its issued authorizations, and any pending transfer. User-facing
dates use a readable UTC format, such as `10 October 2026 at 14:38 UTC`;
seconds are included when relevant. Machine-readable API dates remain ISO 8601.
DTS warns about a recorded plan expiration within three days only when fetching a fresh grant.
Run transfer on the replacement computer. Running it on the already-registered
computer with no pending transfer is a no-op: the confirmation says the computer
is already registered and no transfer is needed, without a redundant timestamp.
An initial registration or an immediate transfer is reported as registered now;
run an `ente` command to request authorization. A scheduled transfer shows its
readable availability date and explains that new authorizations are paused.
The transfer response's availability time is the earliest time an authorization
can be requested, not a new grant's expiration. Transfer requests do not issue
authorizations or change existing token expiry dates.
Hub stops issuing grants during the pending transfer and activates the replacement
only after every old grant expires (at most 24 hours). Switching credentials or profiles does not reset this
per-user registration. These management commands remain available without authorization for `ente`,
but require an ordinary DT2 identity token.

To use local code with a development HTTPS Hub:

```shell
DTSHELL_LIB=/path/to/duckietown-shell/lib \
DTSHELL_COMMANDS=/path/to/duckietown-shell-commands \
DTHUB_HOST=localhost:8443 \
dts devel info
```

`DTHUB_HOST` is a hostname with an optional port; `DTHUB_URL` overrides the full
URL used by the shell. A development Hub using different signing keys requires
an isolated client configured to trust its development public keys. Self-signed
HTTPS certificates must also be trusted; do not disable certificate verification.

This is an official-client policy, not tamper-proof anti-sharing. Machine IDs
can be spoofed or cloned, and public clients can be modified to bypass local
checks. It also does not stop already-running/downloaded robot images. Enforcing
access against hostile clients requires a protected server or image registry.

### Advanced configuration

By default, Duckietown Shell uses the folder `~/dt-data` for storing log data and other cache data.

Alternatively, you can use the `--dt-data` argument to choose a different folder:

    $ dts logs --dt-data ![dir] ![command]

Alternatively, the directory can be specified using the environment variable `DT_DATA`.

    $ DT_DATA=/tmp/data dt logs summary



---------

---------

---------


# TODO

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

[easy_logs]: https://docs-old.duckietown.org/software_devel/out/easy_logs.html

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
