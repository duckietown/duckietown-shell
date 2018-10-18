tag=dt-shell-ubuntu16
name=dt-shell-ubuntu16-container

build-and-test:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN) --build-arg DOCKER_USERNAME=$(DOCKER_USERNAME) .
	$(MAKE) run

build-and-test-no-cache:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN)  --build-arg DOCKER_USERNAME=$(DOCKER_USERNAME) --no-cache .
	$(MAKE) run

run:
	docker run -it \
		-v /var/run/docker.sock:/var/run/docker.sock  \
		-v $(HOME)/.docker:/root/.docker:ro \
		$(tag)

remove:
	docker rm $(name) || true

shell:

	docker run -it --name $(name) $(tag) bash

develop:


	docker run -it \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v $(PWD)/../..:$(PWD)/../.. \
		-v $(DTSHELL_COMMANDS):/commands:ro \
		-v $(HOME)/.docker:/root/.docker:ro \
		-e DTSHELL_COMMANDS=/commands\
	 	-w $(PWD)/../.. --name $(name) $(tag) bash
