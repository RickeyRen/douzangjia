import XCTest
@testable import Douzangjia

final class FeedOptionsTests: XCTestCase {
    private func query(_ options: FeedOptions) -> [String: String] {
        Dictionary(uniqueKeysWithValues: options.queryItems.map { ($0.name, $0.value ?? "") })
    }

    func testDefaultsAddNothingSoTheServerKeepsItsOwnOrder() {
        XCTAssertTrue(FeedOptions().queryItems.isEmpty)
        XCTAssertFalse(FeedOptions().isNarrowed)
    }

    func testRandomSendsItsSeedSoPagesStayInTheSameOrder() {
        var options = FeedOptions()
        options.sort = .random
        options.seed = 42
        XCTAssertEqual(query(options), ["sort": "random", "seed": "42"])
    }

    func testLengthBucketsMatchTheWebBounds() {
        var options = FeedOptions()
        options.length = .short
        XCTAssertEqual(query(options), ["maxDuration": "60"])
        options.length = .medium
        XCTAssertEqual(query(options), ["minDuration": "60", "maxDuration": "300"])
        options.length = .long
        XCTAssertEqual(query(options), ["minDuration": "300"])
    }

    func testPeriodsStartAtLocalMidnightLikeTheWeb() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        // 2026-11-15 15:30 in Shanghai.
        let now = calendar.date(from: DateComponents(year: 2026, month: 11, day: 15, hour: 15, minute: 30))!
        func since(_ period: FeedOptions.Period) -> Date? {
            var options = FeedOptions()
            options.period = period
            return options.queryItems(now: now, calendar: calendar)
                .first { $0.name == "since" }
                .flatMap { $0.value }.flatMap(Double.init).map(Date.init(timeIntervalSince1970:))
        }
        XCTAssertNil(since(.all))
        XCTAssertEqual(since(.week), calendar.date(from: DateComponents(year: 2026, month: 11, day: 8)))
        XCTAssertEqual(since(.quarter), calendar.date(from: DateComponents(year: 2026, month: 8, day: 17)))
        XCTAssertEqual(since(.year), calendar.date(from: DateComponents(year: 2026, month: 1, day: 1)))
    }

    func testGalleriesIgnoreTheLengthBucket() {
        // Galleries have no duration; sending one would empty the list.
        var options = FeedOptions()
        options.kind = .gallery
        options.length = .long
        XCTAssertEqual(query(options), ["type": "gallery"])
        XCTAssertTrue(options.isNarrowed)
    }
}

final class ReviewResponseTests: XCTestCase {
    func testBuildingStateDecodes() throws {
        let body = Data(#"{"state":"building"}"#.utf8)
        guard case .building = try JSONDecoder().decode(ReviewResponse.self, from: body) else {
            return XCTFail("expected building")
        }
    }

    func testSnapshotDecodes() throws {
        let body = Data("""
        {"builtAt": 1794700000, "totals": {"items": 4, "saved": 2, "since": 1786000000},
         "firstMonth": "2026-08", "months": [{"month": "2026-08", "added": 2, "saved": 1}],
         "publishedYears": [{"year": "2025", "count": 3}],
         "topCreators": [{"id": "c1", "name": "阿光", "count": 3, "vanished": 2, "avatarUrl": null}],
         "vanished": {"total": 2, "saved": 1, "lost": 1}}
        """.utf8)
        guard case .ready(let review) = try JSONDecoder().decode(ReviewResponse.self, from: body) else {
            return XCTFail("expected a snapshot")
        }
        XCTAssertEqual(review.totals.items, 4)
        XCTAssertEqual(review.topCreators.first?.name, "阿光")
        XCTAssertNil(review.topCreators.first?.avatarUrl)
        XCTAssertEqual(review.vanished.lost, 1)
    }
}

final class ShareNamingTests: XCTestCase {
    func testNamesAreSafeForFilesAndAirDrop() {
        let name = ShareNaming.base(author: "阿光/AG", title: "山里的清晨: 第1天?\n下集")
        XCTAssertFalse(name.contains("/"))
        XCTAssertFalse(name.contains(":"))
        XCTAssertFalse(name.contains("?"))
        XCTAssertFalse(name.contains("\n"))
        XCTAssertTrue(name.hasPrefix("阿光 AG - 山里的清晨"))
    }

    func testLongTitlesAreShortened() {
        let name = ShareNaming.base(author: "博主", title: String(repeating: "长", count: 100))
        XCTAssertEqual(name.count, "博主 - ".count + 40)
    }

    func testExtensionsFollowTheStoredType() {
        func file(_ type: String, _ mime: String?) -> MediaFile {
            MediaFile(id: 1, index: 0, type: type, byteSize: nil, mimeType: mime, url: "/api/media/1", posterUrl: nil)
        }
        XCTAssertEqual(ShareNaming.fileExtension(file("video", "video/mp4")), "mp4")
        XCTAssertEqual(ShareNaming.fileExtension(file("video", "video/quicktime")), "mov")
        XCTAssertEqual(ShareNaming.fileExtension(file("image", "image/webp")), "webp")
        XCTAssertEqual(ShareNaming.fileExtension(file("image", nil)), "jpg")
        XCTAssertEqual(ShareNaming.fileExtension(file("video", nil)), "mp4")
    }
}

final class PlaybackSpeedTests: XCTestCase {
    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: "playbackSpeed")
        super.tearDown()
    }

    func testUnknownSavedSpeedFallsBackToNormal() {
        UserDefaults.standard.set(Float(3.7), forKey: "playbackSpeed")
        XCTAssertEqual(VideoController.savedSpeed, 1)
        UserDefaults.standard.removeObject(forKey: "playbackSpeed")
        XCTAssertEqual(VideoController.savedSpeed, 1)
    }

    func testChosenSpeedIsRemembered() {
        let controller = VideoController()
        controller.setSpeed(1.5)
        XCTAssertEqual(VideoController.savedSpeed, 1.5)
        XCTAssertEqual(controller.speed, 1.5)
    }
}
