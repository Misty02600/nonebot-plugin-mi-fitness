<div align="center">
    <a href="https://v2.nonebot.dev/store">
    <img src="https://github.com/Misty02600/nonebot-plugin-template/releases/download/assets/NoneBotPlugin.png" width="310" alt="logo"></a>

## ✨ nonebot-plugin-mi-fitness ✨
[![LICENSE](https://img.shields.io/github/license/Misty02600/nonebot-plugin-mi-fitness.svg)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![Adapters](https://img.shields.io/badge/Adapters-OneBot%20v11-blue)](#supported-adapters)
<br/>

[![uv](https://img.shields.io/badge/package%20manager-uv-black?logo=uv)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/code%20style-ruff-black?logo=ruff)](https://github.com/astral-sh/ruff)

</div>

## 📖 介绍

通过小米运动健康的亲友功能，查询用户的心率、睡眠、步数、体重等健康数据。

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-mi-fitness --upgrade
使用 **pypi** 源安装

    nb plugin install nonebot-plugin-mi-fitness --upgrade -i "https://pypi.org/simple"
使用**清华源**安装

    nb plugin install nonebot-plugin-mi-fitness --upgrade -i "https://pypi.tuna.tsinghua.edu.cn/simple"


</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details open>
<summary>uv</summary>

    uv add nonebot-plugin-mi-fitness
安装仓库 main 分支

    uv add git+https://github.com/Misty02600/nonebot-plugin-mi-fitness@main
</details>

<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-mi-fitness
安装仓库 main 分支

    pdm add git+https://github.com/Misty02600/nonebot-plugin-mi-fitness@main
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-mi-fitness
安装仓库 main 分支

    poetry add git+https://github.com/Misty02600/nonebot-plugin-mi-fitness@main
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_mi_fitness"]

</details>

<details>
<summary>使用 nbr 安装(使用 uv 管理依赖可用)</summary>

[nbr](https://github.com/fllesser/nbr) 是一个基于 uv 的 nb-cli，可以方便地管理 nonebot2

    nbr plugin install nonebot-plugin-mi-fitness
使用 **pypi** 源安装

    nbr plugin install nonebot-plugin-mi-fitness -i "https://pypi.org/simple"
使用**清华源**安装

    nbr plugin install nonebot-plugin-mi-fitness -i "https://pypi.tuna.tsinghua.edu.cn/simple"

</details>


## ⚙️ 配置

插件使用 [nonebot_plugin_localstore](https://github.com/nonebot/plugin-localstore) 储存数据和缓存，无需额外配置即可使用。

绑定数据按用户全局存储，用户完成一次绑定后，可在不同群聊和私聊中直接复用。

## 🎉 使用

### 首次使用

1. 超级用户发送 `小米登录`，Bot 会发送二维码
2. 使用小米运动健康 App 扫描二维码完成登录（5 分钟内有效）

### 指令表

| 指令 | 权限 | 需要@ | 范围 | 说明 |
| :--- | :---: | :---: | :---: | :--- |
| `小米绑定 <小米UID>` | 群员 | 否 | 群聊/私聊 | 绑定小米账号，Bot 会自动发送亲友申请 |
| `小米解绑` | 群员 | 否 | 群聊/私聊 | 解除当前绑定 |
| `小米心率` | 群员 | 否 | 群聊/私聊 | 查询今日心率数据 |
| `小米睡眠` | 群员 | 否 | 群聊/私聊 | 查询今日睡眠数据 |
| `小米步数` | 群员 | 否 | 群聊/私聊 | 查询今日步数 |
| `小米体重` | 群员 | 否 | 群聊/私聊 | 查询最近体重记录 |
| `小米日报` | 群员 | 否 | 群聊/私聊 | 查询今日综合健康报告 |
| `小米心率周报` | 群员 | 否 | 群聊/私聊 | 查询近 7 天心率数据 |
| `小米睡眠周报` | 群员 | 否 | 群聊/私聊 | 查询近 7 天睡眠数据 |
| `小米步数周报` | 群员 | 否 | 群聊/私聊 | 查询近 7 天步数数据 |
| `小米登录` | 超级用户 | 否 | 私聊 | 扫码登录小米账号 |
| `小米帮助` | 群员 | 否 | 群聊/私聊 | 查看帮助信息 |

说明：`小米绑定` 为用户级绑定，绑定后可跨群聊/私聊使用；`小米解绑` 也会解除该用户的全局绑定。

### 🎨 效果图
