![astrbot-plugin-mc-sync](https://socialify.git.ci/erzaozi/astrbot_plugin_mc_sync/image?description=1&font=Raleway&forks=1&issues=1&language=1&name=1&owner=1&pattern=Circuit%20Board&pulls=1&stargazers=1&theme=Auto)

# ASTRBOT-PLUGIN-MC-SYNC

- 一个适用于 [AstrBot](https://github.com/Soulter/AstrBot) 的 Minecraft 多平台互通插件

- 基于 [QueQiao（鹊桥）](https://github.com/17TheWord/QueQiao) Mod 的 WebSocket 协议，实现 Minecraft 服务器与 QQ、Telegram、Discord、微信、钉钉等平台之间的**双向消息同步**与**远程控制**

- 支持会话绑定、服务器管理员管理、广播、私聊、Title / ActionBar、RCON 白名单执行，并可将 RCON 能力开放给 LLM 工具调用

> [!TIP]
> 详细的使用教程、配置说明与常见问题请查看 [GitHub Wiki](https://github.com/erzaozi/astrbot_plugin_mc_sync/wiki)，本 README 只提供快速上手。

## 功能列表

- [x] MC ↔ 多平台双向消息同步
- [x] 会话绑定 / 解绑服务器
- [x] 服务器管理员管理
- [x] 服务器状态查询
- [x] 服务器广播与玩家私聊
- [x] Title / ActionBar 消息推送
- [x] RCON 命令白名单执行
- [x] LLM 工具调用 RCON
- [x] 玩家进出 / 死亡 / 成就事件转发
- [x] 网页端配置面板与状态页

## 安装插件

#### 1. 克隆仓库

将插件克隆到 AstrBot 的 plugins 目录：

```
git clone https://github.com/erzaozi/astrbot_plugin_mc_sync.git ./plugins/astrbot_plugin_mc_sync
```

> [!NOTE]
> 如果你的网络环境较差，无法连接到 GitHub，可以使用 [GitHub Proxy](https://ghproxy.link/) 提供的文件代理加速下载服务

#### 2. 安装依赖

```
pip install -r ./plugins/astrbot_plugin_mc_sync/requirements.txt
```

#### 3. 重启 AstrBot

重启后在 AstrBot 中启用该插件即可。

## 依赖 Mod

本插件通过 [QueQiao（鹊桥）](https://github.com/17TheWord/QueQiao) Mod 与 Minecraft 服务端通信，请先在服务端安装对应版本的 QueQiao Mod，并配置好 WebSocket 连接。

## 插件配置

> [!WARNING]
> 推荐使用 AstrBot 网页配置面板（`/astrbot_plugin_mc_sync/config`）修改配置，手动编辑配置文件时请保持 YAML 格式正确。

配置保存在插件数据目录下的 `config.yaml`，单个服务器的配置项如下：

| 配置项 | 说明 |
| ------ | ---- |
| `server_name` | 服务器名（命令中使用的标识） |
| `umo_list` | 绑定到该服务器的会话列表 |
| `cicode_enabled` | 是否启用 CICode 图片 |
| `administrators` | 服务器管理员 UID 列表 |
| `forward_player_join` | 是否转发玩家加入事件 |
| `forward_player_quit` | 是否转发玩家退出事件 |
| `forward_player_death` | 是否转发玩家死亡事件 |
| `forward_player_achievement` | 是否转发玩家成就事件 |
| `rcon_enabled` | 是否允许 RCON |
| `rcon_command_whitelist` | RCON 命令白名单 |

## 命令列表

> 以下命令均为机器人管理员或服务器管理员可用，详细说明见 Wiki。

| 命令 | 功能 |
| ---- | ---- |
| `/sync on <服务器名>` | 将当前会话绑定到指定服务器 |
| `/sync off <服务器名>` | 将当前会话从服务器解绑 |
| `/sync admin-add <服务器名> [UID / @用户]` | 添加服务器管理员 |
| `/sync admin-remove <服务器名> <UID>` | 移除服务器管理员 |
| `/mc status <服务器名>` | 查询服务器状态 |
| `/mc broadcast <服务器名> <消息>` | 向服务器广播消息 |
| `/mc private <服务器名> <玩家ID> <消息>` | 向指定玩家发送私聊 |
| `/mc title <服务器名> <消息>` | 向服务器发送 Title |
| `/mc actionbar <服务器名> <消息>` | 向服务器发送 ActionBar |
| `/mc rcon <服务器名> <命令>` | 在服务器执行 RCON 命令（白名单内） |

## 详细使用方法

完整的安装、配置、命令使用与常见问题请查看 [GitHub Wiki](https://github.com/erzaozi/astrbot_plugin_mc_sync/wiki)。

## 支持与贡献

如果你喜欢这个项目，请不妨点个 Star，这是对开发者最大的动力。

有意见或者建议也欢迎提交 [Issues](https://github.com/erzaozi/astrbot_plugin_mc_sync/issues) 和 [Pull requests](https://github.com/erzaozi/astrbot_plugin_mc_sync/pulls)。

## 许可证

本项目使用 [MIT](https://choosealicense.com/licenses/mit/) 作为开源许可证。