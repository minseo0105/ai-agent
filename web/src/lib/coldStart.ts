/**
 * 서버가 깨어나는 동안 첫 요청이 실패하는 문제를 다룬다.
 *
 * 컨테이너가 잠들어 있다가 깨어나는 배포에서는 화면이 먼저 뜨고 백엔드가 늦게 준비된다.
 * 그 사이의 연결 실패를 "서버가 실행 중인지 확인해 주세요"라고 말하면, 사용자는 자기가
 * 할 수 없는 일을 하라는 말을 듣는다. 잠깐 기다렸다가 몇 번 다시 시도하는 편이 맞다.
 *
 * 다시 시도하는 것은 읽기(GET)처럼 여러 번 불러도 결과가 같은 요청만이다. 쓰기 요청은
 * 같은 일이 두 번 일어날 수 있으므로 여기서 다루지 않는다.
 */
export const COLD_START_DELAYS_MS = [700, 1500, 3000];

/**
 * 다시 시도해도 되는 실패인지. 연결 실패와 502/503/504만 해당한다.
 *
 * 연결 실패는 이름으로 알아본다. instanceof를 쓰면 모듈이 두 번 적재됐을 때 같은 오류가
 * 다른 클래스로 보여 조용히 재시도하지 않게 된다. 이 파일이 다른 모듈을 가져오지 않아야
 * 테스트 실행기에서도 그대로 돌릴 수 있다.
 */
export function isTransient(error: unknown): boolean {
  if ((error as Error)?.name === "ConnectionError") return true;
  const status = (error as { status?: number })?.status;
  return status === 502 || status === 503 || status === 504;
}

export type ColdStartOptions = {
  delays?: number[];
  signal?: AbortSignal;
  /** 재시도에 들어갈 때 화면이 "깨우는 중"이라고 말할 수 있게 알린다. */
  onRetry?: (attempt: number) => void;
  sleep?: (ms: number) => Promise<void>;
};

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * 읽기 요청 하나를 잠깐 기다렸다가 다시 시도한다. 마지막까지 실패하면 그 오류를 그대로 던진다.
 * 취소된 요청은 다시 시도하지 않는다.
 */
export async function withColdStartRetry<T>(
  run: (signal?: AbortSignal) => Promise<T>,
  options: ColdStartOptions = {},
): Promise<T> {
  const delays = options.delays ?? COLD_START_DELAYS_MS;
  const sleep = options.sleep ?? wait;
  let lastError: unknown;
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    if (options.signal?.aborted) throw lastError ?? new Error("cancelled");
    try {
      return await run(options.signal);
    } catch (error) {
      lastError = error;
      if (options.signal?.aborted) throw error;
      if (!isTransient(error) || attempt === delays.length) throw error;
      options.onRetry?.(attempt + 1);
      await sleep(delays[attempt]);
    }
  }
  throw lastError;
}
