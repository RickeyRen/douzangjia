# 抖藏家首页视觉一致性台账

## 对照材料

- 参考页面静默截图：`docs/designs/remnawave-dashboard-reference.jpg`
- 已确认桌面设计规格：`docs/designs/douzangjia-dashboard-desktop.png`
- 已确认手机设计规格：`docs/designs/douzangjia-dashboard-mobile.png`
- 桌面真实数据实现：`docs/designs/douzangjia-dashboard-implementation-desktop.jpg`
- 页面下半部分与 Runtime：`docs/designs/douzangjia-dashboard-implementation-bottom.jpg`
- 430×932 响应式实现：`docs/designs/douzangjia-dashboard-implementation-mobile.jpg`

## 视觉与信息结构对照

| 对照项 | 参考页特征 | 抖藏家实现 | 结论 |
| --- | --- | --- | --- |
| 页面底色 | `#161b22` 黑灰底、弱分割线 | 暗色 token 使用相同底色家族和 `#30363d` 强分割线 | 一致 |
| 信息密度 | 小标题、紧凑指标单元、多列扫描 | 16px 分区标题，桌面 4/3/5 列指标网格 | 一致 |
| 色彩系统 | 蓝、青、绿、橙、紫、红按语义分配 | Phosphor 图标使用六种语义 tone，无单一绿色泛滥 | 一致 |
| 数字样式 | 等宽数字、主值突出、辅助值弱化 | 20px 等宽主值，11–12px 辅助说明 | 一致 |
| 运行时区域 | 每个进程独立彩色顶部边框和明细 | 应用、下载引擎、同步浏览器三张真实运行时卡片 | 领域适配 |
| 趋势 | 运行指标实时变化 | 下载速度和 CPU 负载直接消费指标采样 | 领域适配 |
| 下半页 | 完整呈现 Runtime，而非首屏占位 | 15 个分类进度和 Runtime 均可滚动到达 | 已验证 |
| 手机布局 | 独立紧凑布局、触控目标可用 | 430×932 使用双列卡片、单列趋势和 Runtime、44px 控件 | 已验证 |

## 有意保留的产品差异

- 不复制 Remnawave 的 VPN 用户、带宽或 Node.js Heap 指标；抖藏家只显示能够从 SQLite、Linux `/proc`、磁盘、下载队列和 Chromium 运行状态得到的真实值。
- 桌面应用外壳继续使用抖藏家的收藏分类侧栏；首页内容区只复用参考页的密度、层级、色彩和 Runtime 语言。
- 手机端继续保留抖藏家的五项底部导航，首页为同一真实数据组件的响应式兄弟布局。
- 数据历史不足时显示“数据积累中”，不伪造环比；抖音号未能从远端取得时显示“暂未获取”。

## QA 发现与修正

1. 真实 NAS 中归档数据约 5.1 GB、卷容量约 103.3 TB，整数百分比会错误显示为 `0%`。已改为 `<0.1%`，并增加单元测试。
2. 首页内层滚动容器在桌面实测 `scrollWidth === clientWidth`，没有横向溢出。
3. 430×932 视图采用 iframe 精确约束触发手机断点；标题、双列指标、单列 Runtime 和分类行均完整渲染。
4. 页面下半部分截图确认 15 个分类进度、开关、占用空间、待处理数量和 Runtime 明细均非占位组件。
5. 参考页本身的 Runtime 全页截图出现延迟渲染重复块；抖藏家使用稳定文档流，没有复制该渲染缺陷。

## 当前结论

组件级真实数据渲染、桌面视觉、下半页和 430×932 布局已通过。生产 NAS 容器已部署并健康；最终生产外壳截图仍需内置浏览器拥有本地管理员会话后完成。
