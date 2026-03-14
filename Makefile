all:
	cat Makefile

.NOTPARALLEL: capture_all

build:
	cc -O2 -Wno-unused-result -o monitor-bin monitor.c -lpthread

test-c: build
	bash test_c.sh
	uv run pytest test_monitor.py -v

test-python: build
	uv run pytest test_monitor.py -v

test: test-c

capture:
	@test -n "$(AGENT)" || (echo "Usage: make capture AGENT=<claude|codex|copilot|gemini|vibe|qwen> [DUR=60]"; exit 1)
	./capture_fixture.sh $(AGENT) $(DUR)

capture_claude:
	$(MAKE) capture AGENT=claude DUR="$(DUR)"

capture_codex:
	$(MAKE) capture AGENT=codex DUR="$(DUR)"

capture_copilot:
	$(MAKE) capture AGENT=copilot DUR="$(DUR)"

capture_gemini:
	$(MAKE) capture AGENT=gemini DUR="$(DUR)"

capture_vibe:
	$(MAKE) capture AGENT=vibe DUR="$(DUR)"

capture_qwen:
	$(MAKE) capture AGENT=qwen DUR="$(DUR)"

capture_all: capture_claude capture_codex capture_copilot capture_gemini capture_vibe capture_qwen

# Manual tmux test — no agent needed, just pipes text through a plain session.
# Open a second terminal and run: echo "status" | nc -U /tmp/test-monitor.sock
tmux-test:
	tmux new-session -d -s monitor-test 2>/dev/null || true
	tmux pipe-pane -t monitor-test "python $(CURDIR)/monitor.py --agent claude --socket /tmp/test-monitor.sock"
	@echo "Session running. Send lines with:"
	@echo "  tmux send-keys -t monitor-test:0.0 -l -- 'Thinking...'"
	@echo "  sleep 0.1"
	@echo "  tmux send-keys -t monitor-test:0.0 C-m"
	@echo "Query state with:"
	@echo "  echo status | nc -U /tmp/test-monitor.sock"
	@echo "Attach with:"
	@echo "  tmux attach -t monitor-test"

tmux-clean:
	tmux kill-session -t monitor-test 2>/dev/null || true
	rm -f /tmp/test-monitor.sock
