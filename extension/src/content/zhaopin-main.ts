// 智联 MAIN-world hook 入口：经 manifest "world": "MAIN" 声明式注入（扩展
// 注入不受页面 CSP 约束），document_start 尽早包裹 fetch/XHR。截获的
// fe-api 响应经 postMessage 桥交 content/zhaopin.ts（isolated world）。
import { installZhaopinHook } from "../shared/platforms/zhaopin";

installZhaopinHook(window);
