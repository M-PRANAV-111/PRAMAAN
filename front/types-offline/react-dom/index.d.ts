declare module "react-dom/client" {
  export function createRoot(el: Element): { render(node: React.ReactNode): void; unmount(): void };
}
