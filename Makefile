# 日想観：阿字池に沈む夕日と鳳凰堂（Blender で光を焼き、three.js で描く）
BYODOIN ?= ../byodoin
BLEND   := $(BYODOIN)/build/byodoin.blend
BLENDER ?= blender
PY      ?= .venv/bin/python
BAKE    := build/bake
PORT    ?= 8793
DUR     ?= 21

.PHONY: setup scene bake sound serve frames video clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/playwright install chrome || true

# 平等院鳳凰堂のシーン（aiimpl/byodoin）を組み立てる
scene:
	test -d $(BYODOIN) || git clone https://github.com/aiimpl/byodoin $(BYODOIN)
	$(MAKE) -C $(BYODOIN) all

# 夕日の光を焼き付ける（M5 の MacBook で建物 約45分、木と地形 約40分）
bake:
	mkdir -p $(BAKE)
	$(BLENDER) -b $(BLEND) -P bake/sky.py -- $(BAKE)
	$(BLENDER) -b $(BLEND) -P bake/bake_hall.py -- $(BAKE)
	$(BLENDER) -b $(BLEND) -P bake/bake_env.py -- $(BAKE)

sound:
	mkdir -p build
	cd sound && ../$(PY) compose.py ../build/nissokan.wav

# http://127.0.0.1:8793/web/ で開く（焼いたデータ build/bake を読む）
serve:
	python3 -m http.server $(PORT) --bind 127.0.0.1

# 630 コマを書き出す（サーバーを裏で立てる）
frames:
	python3 -m http.server $(PORT) --bind 127.0.0.1 >/dev/null 2>&1 & echo $$! > build/server.pid; \
	sleep 1; URL="http://127.0.0.1:$(PORT)/web/index.html?render" $(PY) tools/render.py build/frames --range 0 $(DUR) 30; \
	kill `cat build/server.pid`; rm -f build/server.pid

video: sound frames
	tools/encode.sh build/frames build/nissokan.wav build/nissokan.mp4

clean:
	rm -rf build
