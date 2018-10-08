all:


bump-upload:
	$(MAKE) bump
	$(MAKE) upload
	
bump:
	bumpversion patch

upload:
	git push --tags
	git push
	rm -f dist/*
	python setup.py sdist
	twine upload dist/*


branch=$(shell git rev-parse --abbrev-ref HEAD)

tag_rpi=duckietown/rpi-duckietown-shell:$(branch)
tag_x86=duckietown/laptop-duckietown-shell:$(branch)

build: build-rpi build-x86

push: push-rpi push-x86

build-rpi:
	docker build -t $(tag_rpi) -f Dockerfile.rpi .

build-x86:
	docker build -t $(tag_x86) -f Dockerfile.x86 .

push-rpi:
	docker push $(tag_rpi)

push-x86:
	docker push $(tag_x86)

