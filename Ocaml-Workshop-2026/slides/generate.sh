#!/usr/bin/env sh

set -eu
cd "$(dirname "$0")"

pandoc src/*.md \
  -t beamer \
  --pdf-engine=xelatex \
  --slide-level=2 \
  -o slides.pdf
