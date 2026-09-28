#!/bin/bash
# 連番 PNG（30fps）と音を、X に上げられる形式の mp4 にする: encode.sh コマのディレクトリ 音.wav 出力.mp4
set -e
ffmpeg -v error -y -framerate 30 -i "$1/%05d.png" -i "$2" \
  -vf "scale=1920:1080:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p" \
  -c:v libx264 -profile:v high -crf 16 -preset slow -pix_fmt yuv420p -color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -c:a aac -b:a 192k -shortest -movflags +faststart "$3"
ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt,color_range,width,height,nb_frames -of csv=p=0 "$3"
