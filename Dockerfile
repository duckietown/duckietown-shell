FROM billyteves/ubuntu-dind:16.04

COPY . duckietown-shell

RUN apt-get update && apt-get install -y \
	python-pip \
	git \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /duckietown-shell

# copy the requirements.txt only, first
# changes to the code don't require re-running this
COPY requirements.txt .
# install requirements
RUN pip install -r requirements.txt
# copy the rest  
COPY . .
#   Note the contents of .dockerignore:
#
#     **
#     !requirements.txt
#     !lib
#     !setup.py
#     !README.md
#
#   That's all we need - do not risk including spurious files.


# Install the package using '--no-deps': you want to pin everything
# using requirements.txt
# So, we want this to fail if we forgot anything.
#RUN pip install --prefix /usr --no-deps .
RUN pip install .

ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

#ENTRYPOINT ["dts"]
