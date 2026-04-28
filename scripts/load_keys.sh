#!/usr/bin/env bash


export OPENROUTER_API_KEY=$(security find-generic-password -s "OPENROUTER_API_KEY" -w)

# export GEMINI_API_KEY=$(security find-generic-password -s "GEMINI_API_KEY" -w)
# export DEEPSEEK_API_KEY=$(security find-generic-password -s "DEEPSEEK_API_KEY" -w)
# export QWEN_API_KEY=$(security find-generic-password -s "QWEN_API_KEY" -w)
# export ANTHROPIC_API_KEY=$(security find-generic-password -s "ANTHROPIC_API_KEY" -w)