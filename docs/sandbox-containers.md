# Container isolation (community edition)

MOVO can run governed scripts in one-shot containers and DSH plugins in separate per-profile Runtime containers. The feature is optional during rollout; the existing execution path remains in use until it is enabled. Docker Engine 26 or newer is required for per-job volume subpaths.

## Enable

Add these lines to the deployment `.env` file, then run `./movo up --build` for a source deployment or `./movo update` once the sandbox images have been published:

```dotenv
COMPOSE_PROFILES=sandbox
MOVO_SANDBOX_MANAGER_URL=http://sandbox-manager:8300
MOVO_SANDBOX_MAX_CONCURRENT=2
MOVO_SANDBOX_MAX_PENDING=8
MOVO_SANDBOX_PLUGIN_IDLE_SECONDS=900
```

The manager and egress proxy run as separate Compose services. The manager alone has access to the Docker socket. Script jobs receive a private workspace and internal Docker network. Plugin Runtime containers receive storage scoped to their Runtime isolation key. Network egress is available through the proxy, which rejects private and local destinations. Admin → Settings → Sandbox containers shows current health and counts.

The script concurrency setting limits active one-shot containers. Requests beyond the limit wait up to 20 seconds, with at most `MOVO_SANDBOX_MAX_PENDING` queued. Administrators can adjust the queue limit in Settings; the saved value persists across manager restarts. The concurrency limit remains a deployment setting. A plugin Runtime is reclaimed after the idle timeout; its session storage remains available for the next turn. The first turn after reclamation must start a new container and may take several seconds.

## Packaged Skills

MOVO accepts a Skill ZIP with one `SKILL.md` and up to 20,000 files, 100 MiB compressed, and 200 MiB expanded. A repository ZIP may place the sole Skill in a deeper directory; MOVO keeps only that Skill subtree and stores a canonical ZIP. An invoked Skill's package is cached by its content digest. Each script job mounts that package read-only under `/job/skills` and receives a separate writable `/job` directory. Script code can use `skill_dir` for the exact package root and `output_dir` for files that should be delivered to the user. The first execution extracts the package; subsequent jobs reuse the cached read-only copy.

The DSH text resource reader caches the compressed archive and extracts only the requested UTF-8 entry. Reading Skill instructions does not unpack thousands of templates into the Runtime Host. This cache is separate from the script execution cache because the two components use different volumes.

The container uses the configured script image's dependencies. A Skill that needs packages or system binaries absent from that image may require a purpose-built script image selected with `MOVO_SANDBOX_SCRIPT_IMAGE`. This is an operator-controlled image setting, not a model-provided image name. Installing arbitrary dependencies from a Skill archive during a user request is not part of the current execution path.

Do not mount the Docker socket into the chat API, the DSH Host, or the job containers. The manager creates containers from fixed images and commands; requests cannot supply arbitrary Docker configuration.
