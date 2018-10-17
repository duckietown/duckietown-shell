tag=dt-shell-ubuntu
name=dt-shell-ubuntu-container

build:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN) .

build-no-cache:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN)  --no-cache .

remove:
	docker rm $(tag) || true

shell:

	docker run -it --name $(name) $(tag)

develop:

	docker run -it -v $(PWD)/..:/duckietown-shell -v $(DTSHELL_COMMANDS):/commands:ro \
	-e DTSHELL_COMMANDS=/commands\
	 -w /duckietown-shell --name $(name) $(tag)
