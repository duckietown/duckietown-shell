tag=dt-shell-ubuntu18
name=dt-shell-ubuntu18-container

build-and-test:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN) --build-arg DOCKER_USERNAME=$(DOCKER_USERNAME) .
	$(MAKE) run

build-and-test-no-cache:
	docker build -t $(tag) --build-arg TOKEN=$(DUCKIETOWN_TOKEN)  --build-arg DOCKER_USERNAME=$(DOCKER_USERNAME) --no-cache .
	$(MAKE) run

run:
	rm -rf /tmp/ubuntu18-tests
	docker run -it \
		-v /var/run/docker.sock:/var/run/docker.sock  \
		-w /tmp/ubuntu18-tests \
		-v $(HOME)/.docker:/root/.docker:ro \
		$(tag) /dts-test/20_challenges_submit.sh

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
		--privileged\
	 	-w $(PWD)/../.. \
	 	-e PS1='\${debian_chroot:+(\$debian_chroot)}\[\033[01;32m\]\u\[\033[00m\]:\[\033[01;34m\]\W\[\033[00m\]\$ ' \
	 	--name $(name) $(tag) bash
#     PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u\[\033[00m\]:\[\033[01;34m\]\W\[\033[00m\]\$ '
