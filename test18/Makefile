all:
	docker build -t dt-shell-ubuntu .

shell:
	docker rm dt-shell-ubuntu
	docker run -it --rm  --name dt-shell-ubuntu dt-shell-ubuntu
