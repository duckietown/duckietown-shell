build:
	docker build -t dt-shell-ubuntu .

remove:
	docker rm dt-shell-ubuntu || true

shell:

	docker run -it --name dt-shell-ubuntu dt-shell-ubuntu

develop:

	docker run -it -v $(PWD)/..:/duckietown-shell -v $(DTSHELL_COMMANDS):/commands:ro \
	-e DTSHELL_COMMANDS=/commands\
	 -w /duckietown-shell --name dt-shell-ubuntu dt-shell-ubuntu
