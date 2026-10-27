from __future__ import annotations


_ENGLISH_MESSAGES = {
    "系统尚未完成初始化，请先在管理后台执行 Setup": "Setup is incomplete. Finish setup in the admin console.",
    "用户名或密码错误": "Incorrect username or password",
    "当前账号未绑定有效组织，请联系管理员配置租户ID": "This account has no valid organization. Contact an administrator.",
    "请选择要进入的组织": "Choose an organization to enter",
    "组织ID无效，请联系管理员配置租户ID": "Invalid organization ID. Contact an administrator.",
    "登录挑战不存在或已失效": "The sign-in challenge is unavailable or invalid",
    "登录挑战已过期": "The sign-in challenge has expired",
    "组织ID无效": "Invalid organization ID",
    "所选组织不可用": "The selected organization is unavailable",
    "用户数据异常": "Invalid user data",
    "用户不存在或已禁用": "User not found or disabled",
    "当前账号不可切换到该组织": "This account cannot switch to that organization",
    "组织内用户不存在或已禁用": "User not found or disabled in this organization",
    "用户名称不能为空": "User name is required",
    "个人资料已更新": "Profile updated",
    "头像仅支持 JPG、PNG 或 WebP 图片": "Avatar must be a JPG, PNG, or WebP image",
    "头像文件不能为空": "Choose an avatar file",
    "头像文件格式无效": "Invalid avatar file format",
    "头像已更新": "Avatar updated",
    "个人空间没有管理后台": "Personal spaces have no admin console",
    "您没有访问管理后台的权限": "You do not have access to the admin console",
    "单点登录凭证授权成功": "Single sign-on authorized",
}


def localized_auth_message(message: str, accept_language: str | None) -> str:
    language = (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return message
    return _ENGLISH_MESSAGES.get(message, "Authentication failed")
