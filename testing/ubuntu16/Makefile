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
	docker rm $(tag) || true

shell:

	docker run -it --name $(name) $(tag)

develop:

	docker run -it -v $(PWD)/../..:/duckietown-shell -v $(DTSHELL_COMMANDS):/commands:ro \
	-e DTSHELL_COMMANDS=/commands\
	 -w /duckietown-shell --name $(name) $(tag)
