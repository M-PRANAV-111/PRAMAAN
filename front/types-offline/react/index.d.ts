declare module "react" {
  namespace React {
    type ReactNode = ReactElement | string | number | bigint | boolean | null | undefined | Iterable<ReactNode>;
    interface ReactElement { type: unknown; props: unknown; key: string | null }
    type Key = string | number;
    type SetStateAction<S> = S | ((prev: S) => S);
    type Dispatch<A> = (value: A) => void;
    interface RefObject<T> { current: T }
    interface Context<T> { Provider: (props: { value: T; children?: ReactNode }) => ReactElement }
    type CSSProperties = Record<string, string | number | undefined>;
    interface SyntheticEvent<T = Element> { currentTarget: T; target: EventTarget; preventDefault(): void; stopPropagation(): void }
    interface FormEvent<T = Element> extends SyntheticEvent<T> {}
    interface ChangeEvent<T = Element> extends SyntheticEvent<T> { target: EventTarget & T }
    interface MouseEvent<T = Element> extends SyntheticEvent<T> { button: number; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }
    interface KeyboardEvent<T = Element> extends SyntheticEvent<T> { key: string; getModifierState(key: string): boolean }
    interface FocusEvent<T = Element> extends SyntheticEvent<T> {}
    interface DragEvent<T = Element> extends SyntheticEvent<T> { dataTransfer: DataTransfer }
    type FC<P = object> = (props: P) => ReactElement | null;

    function useState<S>(initial: S | (() => S)): [S, Dispatch<SetStateAction<S>>];
    function useState<S = undefined>(): [S | undefined, Dispatch<SetStateAction<S | undefined>>];
    function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
    function useLayoutEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
    function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
    function useCallback<T extends (...args: any[]) => unknown>(cb: T, deps: readonly unknown[]): T;
    function useRef<T>(initial: T): RefObject<T>;
    function useContext<T>(ctx: Context<T>): T;
    function useId(): string;
    function useSyncExternalStore<T>(subscribe: (cb: () => void) => () => void, get: () => T): T;
    function createContext<T>(value: T): Context<T>;
    function lazy<T extends (props: any) => ReactElement | null>(load: () => Promise<{ default: T }>): T;
    const Suspense: (props: { fallback?: ReactNode; children?: ReactNode }) => ReactElement;
    const Fragment: (props: { children?: ReactNode }) => ReactElement;
    const StrictMode: (props: { children?: ReactNode }) => ReactElement;
  }
  export = React;
}
declare module "react/jsx-runtime" {
  export const jsx: unknown;
  export const jsxs: unknown;
  export const Fragment: unknown;
}
declare namespace JSX {
  type Element = import("react").ReactElement;
  interface ElementChildrenAttribute { children: object }
  interface IntrinsicAttributes { key?: import("react").Key }
  interface IntrinsicElements { [name: string]: any }
}
