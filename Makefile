all:

PYTHON ?= python3
WHEELHOUSE ?= wheelhouse
DIST ?= dist
.PHONY: release-deps release-wheels release-seal release-verify upload

release-deps:
	$(PYTHON) -m pip install -r requirements-release.txt

release-wheels:
	$(PYTHON) -m cibuildwheel --output-dir "$(WHEELHOUSE)"

release-seal:
	$(PYTHON) tools/release.py seal "$(WHEELHOUSE)"

release-verify:
	$(PYTHON) tools/release.py verify "$(DIST)" --require-matrix

bump-upload:
	@echo "Use the Automated Release workflow to bump and publish all native platforms."
	@echo "Use make upload only after placing the complete signed wheel matrix in $(DIST)."
	@exit 1

bump: # v2
	bumpversion patch
	git push --tags
	git push



upload:
	$(PYTHON) tools/release.py publish "$(DIST)"



branch=$(shell git rev-parse --abbrev-ref HEAD)

tag_rpi=duckietown/rpi-duckietown-shell:$(branch)
tag_x86=duckietown/duckietown-shell:$(branch)

build: build-rpi build-x86

push: push-rpi push-x86

build-rpi:
	docker build -t $(tag_rpi) -f Dockerfile.rpi .

build-x86:
	docker build -t $(tag_x86) -f Dockerfile .

build-x86-no-cache:
	docker build -t $(tag_x86) -f Dockerfile --no-cache .

push-rpi:
	docker push $(tag_rpi)

push-x86:
	docker push $(tag_x86)

test:
	make -C testing

black:
	black -l 110 lib

pre-circle-tests:
	git --help

post-circle-tests:
	git --help
	dts --set-version daffy
	dts help
	dts version
