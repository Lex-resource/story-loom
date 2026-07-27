import { useCallback, useEffect, useRef, useState } from 'react';

import { BACKEND_URL } from '../services/api';
import {
  EvaluationsStreamParser,
  StreamingJsonFieldParser,
  ValidatorStreamParser,
} from '../utils/streamingJsonParser';

export const MAX_RECONNECT_ATTEMPTS = 5;

export function shouldApplyChapterStreaming(autoFollow, messageChapterIndex, activeChapterIndex) {
  return autoFollow || !messageChapterIndex || messageChapterIndex === activeChapterIndex;
}

function buildWebSocketUrl(projectId) {
  try {
    const parsed = new URL(BACKEND_URL);
    const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${parsed.host}/api/writing/ws/${projectId}`;
  } catch {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/writing/ws/${projectId}`;
  }
}

export default function useProjectRealtime({ projectId, onMessage, onOpen, onLog, onError }) {
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef(null);
  const projectIdRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const intentionalCloseRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const editorParserRef = useRef(null);
  const evaluationsParserRef = useRef(null);
  const validatorParserRef = useRef(null);
  const callbacksRef = useRef({ onMessage, onOpen, onLog, onError });
  callbacksRef.current = { onMessage, onOpen, onLog, onError };

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    const socket = socketRef.current;
    socketRef.current = null;
    projectIdRef.current = null;
    setIsConnected(false);
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
  }, []);

  const connect = useCallback((nextProjectId) => {
    if (!nextProjectId) return;
    const existing = socketRef.current;
    if (existing && projectIdRef.current === nextProjectId && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) return;
    disconnect();
    intentionalCloseRef.current = false;
    const socket = new WebSocket(buildWebSocketUrl(nextProjectId));
    socketRef.current = socket;
    projectIdRef.current = nextProjectId;

    socket.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setIsConnected(true);
      callbacksRef.current.onOpen?.(nextProjectId);
    };
    socket.onmessage = (event) => {
      try {
        callbacksRef.current.onMessage?.(JSON.parse(event.data));
      } catch (error) {
        callbacksRef.current.onError?.(error, 'parse');
      }
    };
    socket.onclose = () => {
      if (socketRef.current === socket) {
        socketRef.current = null;
        projectIdRef.current = null;
      }
      setIsConnected(false);
      if (intentionalCloseRef.current) {
        intentionalCloseRef.current = false;
        return;
      }
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        callbacksRef.current.onLog?.('系统', `WebSocket 重连已达最大次数 (${MAX_RECONNECT_ATTEMPTS})，停止重连。请手动刷新页面。`, 'error');
        return;
      }
      const attempt = reconnectAttemptsRef.current;
      reconnectAttemptsRef.current += 1;
      const delay = Math.min(5000 * 2 ** attempt, 30000);
      callbacksRef.current.onLog?.('系统', `WebSocket 连接已断开，${delay / 1000}秒后尝试第 ${attempt + 1}/${MAX_RECONNECT_ATTEMPTS} 次重连...`, 'error');
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        if (!intentionalCloseRef.current) connect(nextProjectId);
      }, delay);
    };
    socket.onerror = (error) => {
      setIsConnected(false);
      callbacksRef.current.onError?.(error, 'socket');
    };
  }, [disconnect]);

  const resetEditorParsers = useCallback(() => {
    editorParserRef.current = new StreamingJsonFieldParser('edited_content');
    evaluationsParserRef.current = new EvaluationsStreamParser();
  }, []);

  const resetValidatorParser = useCallback(() => {
    validatorParserRef.current = new ValidatorStreamParser();
  }, []);

  const resetParsers = useCallback(() => {
    editorParserRef.current = null;
    evaluationsParserRef.current = null;
    validatorParserRef.current = null;
  }, []);

  const appendEditorChunk = useCallback((text) => {
    if (!editorParserRef.current || !evaluationsParserRef.current) resetEditorParsers();
    const previousLength = editorParserRef.current.valueBuffer.length;
    editorParserRef.current.append(text);
    return {
      content: editorParserRef.current.valueBuffer.slice(previousLength),
      evaluations: evaluationsParserRef.current.append(text),
    };
  }, [resetEditorParsers]);

  const appendValidatorChunk = useCallback((text) => {
    if (!validatorParserRef.current) resetValidatorParser();
    return validatorParserRef.current.append(text);
  }, [resetValidatorParser]);

  useEffect(() => {
    resetParsers();
    if (projectId) connect(projectId);
    else disconnect();
    return disconnect;
  }, [connect, disconnect, projectId, resetParsers]);

  return {
    isConnected,
    disconnect,
    resetEditorParsers,
    resetValidatorParser,
    appendEditorChunk,
    appendValidatorChunk,
  };
}
