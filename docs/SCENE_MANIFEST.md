# 扩展一个剧情场景

剧情设定和舞台配置分开维护：人物、事实、地点与道具属于 `SceneSpec`；颜色、布景与相机属于 `scene_manifest`。舞台只读取状态，不负责生成或提交剧情。

在 `scene_manifests/` 增加一个 JSON 文件，设置唯一 `scene_key`。Vite 会加载目录内的配置。场景数据中的 `scene_manifest` 同名字段可覆盖文件默认值。例如：

```json
{
  "scene_key": "cafe",
  "name": "雨夜咖啡馆",
  "renderer_type": "generic3d",
  "zones": [
    {"id":"咖啡馆","position":[0,0,0]},
    {"id":"咖啡馆·入口","position":[6,0,0]}
  ],
  "camera_presets": [
    "wide", "top", "focus",
    {"id":"door","label":"入口","position":[10,5,6],"target":[6,0.8,0]}
  ],
  "asset_set": ["table", "chairs", "plants", "cabinet"],
  "character_style": "procedural_low_poly",
  "character_colors": ["#617d75", "#ad7962", "#7f7799"],
  "palette": {"floor":"#d3c1a4","wall":"#e2d8c6","wood":"#846b54","accent":"#617d75"},
  "interaction_points": [
    {"id":"letter","label":"信件区","position":[0,1.12,0],"item_id":"letter"}
  ]
}
```

创建场景时使用 `scene_manifest: {"scene_key":"cafe"}`，并在 `locations` 中设置相同的地点名字。也可以把上述配置直接放进创建场景的 `scene_manifest`。舞台按世界中的地点显现角色，`zones[].id` 必须与地点名字一致；未配置坐标的地点会自动排列。

当前程序化布景支持 `table`、`chairs`、`screen`、`plants`、`cabinet`。剧情道具始终来自状态里的 `items`，不会因为布景缺少模型而消失；无持有者的道具可用交互点定位，持有人优先。交互点是可视位置标记，实际拾取或交付仍由剧情引擎裁定。

`renderer_type: "map"` 或 `"2.5d"` 可指定状态地图。未知场景或角色样式使用通用程序化低多边形占位，WebGL 不可用或丢失上下文时回退到 2.5D。新增专属复杂模型需要增加渲染组件；新增剧情样例和通用布景配置不需要修改剧情引擎。

当前内置董事会、客栈、古宅、办公室与通用场景。默认离线模式的想法拆解使用可编辑模板，不把它当作自由题材的语义理解模型。
