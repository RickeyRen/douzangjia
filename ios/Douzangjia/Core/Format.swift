import SwiftUI

enum Format {
    static func bytes(_ value: Int?) -> String {
        guard let value else { return "—" }
        return ByteCountFormatter.string(fromByteCount: Int64(value), countStyle: .file)
    }

    static func speed(_ bytesPerSecond: Double) -> String {
        bytesPerSecond > 0 ? bytes(Int(bytesPerSecond)) + "/s" : "—"
    }

    static func integer(_ value: Int) -> String {
        value.formatted(.number.grouping(.automatic))
    }

    static func eta(_ seconds: Int?) -> String {
        guard let seconds, seconds > 0 else { return "—" }
        if seconds < 60 { return "\(seconds) 秒" }
        if seconds < 3600 { return "\(Int((Double(seconds) / 60).rounded())) 分钟" }
        return String(format: "%.1f 小时", Double(seconds) / 3600)
    }

    static func relative(_ unixSeconds: Int?) -> String {
        guard let unixSeconds else { return "从未" }
        let delta = Date().timeIntervalSince1970 - Double(unixSeconds)
        if delta < 45 { return "刚刚" }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.unitsStyle = .full
        return formatter.localizedString(for: Date(timeIntervalSince1970: Double(unixSeconds)), relativeTo: Date())
    }

    static func date(_ unixSeconds: Int) -> String {
        Date(timeIntervalSince1970: Double(unixSeconds))
            .formatted(.dateTime.year().month().day().locale(Locale(identifier: "zh_CN")))
    }

    /// Douyin-style counts: 1.7万, 9.9万, 1.2亿.
    static func compact(_ value: Int) -> String {
        if value >= 100_000_000 { return String(format: "%.1f亿", Double(value) / 100_000_000) }
        if value >= 10_000 { return String(format: "%.1f万", Double(value) / 10_000) }
        return integer(value)
    }

    static func dateTime(_ unixSeconds: Int) -> String {
        Date(timeIntervalSince1970: Double(unixSeconds))
            .formatted(.dateTime.month().day().hour().minute().locale(Locale(identifier: "zh_CN")))
    }

    static func duration(_ milliseconds: Int?) -> String? {
        guard let milliseconds, milliseconds > 0 else { return nil }
        let total = milliseconds / 1000
        return String(format: "%d:%02d", total / 60, total % 60)
    }

    static func errorText(_ code: String?) -> String? {
        guard let code else { return nil }
        let known: [String: String] = [
            "DOWNLOAD_FAILED": "下载失败",
            "MEDIA_URL_EXPIRED": "下载链接过期，正在重新获取",
            "MEDIA_URL_UNAVAILABLE": "暂时拿不到新的下载链接",
            "MEDIA_HTTP_ERROR": "抖音服务器拒绝了下载",
            "MEDIA_GONE": "抖音上已找不到这个作品",
            "STORAGE_FULL": "NAS 空间不足",
            "RATE_LIMITED": "抖音限制了访问频率",
            "DOUYIN_SESSION_EXPIRED": "抖音登录已失效",
            "SESSION_EXPIRED": "抖音登录已失效",
            "SYNC_INTERRUPTED": "同步被中断",
            "SYNC_TIMEOUT": "同步耗时过长，已重启后台浏览器",
            "NETWORK_TIMEOUT": "访问抖音超时",
        ]
        return known[code] ?? code
    }
}
