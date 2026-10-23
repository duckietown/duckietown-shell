from pathlib import Path
import time

import dt_shell_device
from dt_shell import DTCommandAbs, UserError, dtslogger
from dt_shell.viewer import ViewerSession, host_info, new_context


class DTCommand(DTCommandAbs):
    help = "Prepare a staff/superuser Viewer developer session for direct source/container launches"

    @staticmethod
    def command(shell, args, **kwargs):
        parsed = DTCommand._resolve_parsed(args, kwargs.get("parsed"))
        directory = Path(parsed.directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        context, tickets = new_context(
            app=parsed.app, endpoint=parsed.url, backend="0" * 64, backend_image="0" * 64,
            desktop=None, desktop_device=dt_shell_device.get_device_id(), development=True,
        )
        paths = [directory / "backend.json", directory / "desktop.json"]
        if any(path.exists() or path.is_symlink() for path in paths):
            raise UserError("The developer handoff directory already contains session files. Use an empty directory.")
        session = ViewerSession(shell, app=parsed.app, context=context, os_family=host_info()["platform"])
        created = []
        try:
            for consumer, path in zip(("backend", "desktop"), paths):
                if path.exists() or path.is_symlink():
                    raise UserError("The developer handoff directory already contains session files. Use an empty directory.")
                session.write_handoff(
                    path, consumer=consumer, ticket=tickets["ready" if consumer == "backend" else "desktop"],
                    broker_host=parsed.broker_host,
                )
                created.append(path)
            dtslogger.info(f"Developer handoffs: {paths[0]} and {paths[1]}. Keep this DTS process running.")
            dtslogger.info(parsed.url.replace("/app/", "/__viewer__/open#") + tickets["browser"])
            while session.error is None:
                time.sleep(1)
            raise UserError(session.error)
        except KeyboardInterrupt:
            dtslogger.info("Closing the Viewer developer session.")
        finally:
            session.close()
            for path in created:
                path.unlink(missing_ok=True)
