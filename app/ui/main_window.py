from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.capture.models import WindowInfo
from app.capture.stability import StableFrameSelector
from app.capture.win32_capture import Win32WindowCapture
from app.capture.window_locator import list_visible_windows
from app.cards.catalog import (
    ArtworkRepository,
    CardCatalog,
    CardNameLocalizer,
    CardRecord,
)
from app.cards.features import FeatureIndex, LocatedCardMatch
from app.combos.models import ComboGraph, RouteCandidate
from app.deck_packs.loader import load_deck_pack
from app.deck_packs.models import DeckPack
from app.decks.models import DeckList
from app.roi.models import NormalizedROI, ROIProfile
from app.roi.render import render_roi_overlay
from app.recognition.snapshot_analyzer import SnapshotAnalysis, SnapshotAnalyzer
from app.sessions.manager import AnalysisResult, SessionManager
from app.state.models import Phase, UsageState
from app.state.observation import BoardObservation


class MainWindow(QMainWindow):
    def __init__(self, *, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.profile_path = (
            project_root / "roi-profiles" / "md-zh-hans-1920x1080.json"
        )
        self.capture_dir = project_root / "data" / "captures"
        self.deck_dir = project_root / "data" / "decks"
        self.card_data_dir = project_root / "data" / "cards"
        self.catalog = CardCatalog(self.card_data_dir / "catalog.json")
        self.card_name_localizer = CardNameLocalizer(
            self.card_data_dir / "names.zh-Hans.json"
        )
        self.artwork_repository = ArtworkRepository(self.card_data_dir / "images")
        self.current_deck: DeckList | None = None
        self.current_deck_pack: DeckPack | None = None
        self.current_feature_index: FeatureIndex | None = None
        self.current_card_records: dict[int, CardRecord] = {}
        self.snapshot_analysis: SnapshotAnalysis | None = None
        self.current_graph: ComboGraph | None = None
        self.session_manager: SessionManager | None = None

        self.profile = ROIProfile.load(self.profile_path)
        self.window_items: list[WindowInfo] = []
        self.raw_frame: np.ndarray | None = None
        self.preview_frame: np.ndarray | None = None

        self.capture_provider = Win32WindowCapture()
        self.stable_selector = StableFrameSelector()

        self.setWindowTitle("YGO Combo Navigator — 0.2.0")
        self.resize(1420, 860)
        self.setStatusBar(QStatusBar(self))

        self._build_ui()
        self._populate_regions()
        self.refresh_windows()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(420)

        refresh_button = QPushButton("刷新窗口")
        refresh_button.clicked.connect(self.refresh_windows)
        capture_button = QPushButton("截取稳定画面")
        capture_button.clicked.connect(self.capture_selected_window)
        open_button = QPushButton("打开本地截图")
        open_button.clicked.connect(self.open_local_image)
        save_button = QPushButton("保存调试图")
        save_button.clicked.connect(self.save_debug_images)
        import_pack_button = QPushButton("导入卡组包")
        import_pack_button.clicked.connect(self.import_deck_pack)
        analyze_button = QPushButton("分析当前截图")
        analyze_button.clicked.connect(self.analyze_current_snapshot)

        toolbar.addWidget(QLabel("目标窗口："))
        toolbar.addWidget(self.window_combo, 1)
        toolbar.addWidget(refresh_button)
        toolbar.addWidget(capture_button)
        toolbar.addWidget(open_button)
        toolbar.addWidget(save_button)
        toolbar.addWidget(import_pack_button)
        toolbar.addWidget(analyze_button)
        root_layout.addLayout(toolbar)

        self.deck_info_label = QLabel("当前卡组包：未导入")
        root_layout.addWidget(self.deck_info_label)

        session_toolbar = QHBoxLayout()
        new_session_button = QPushButton("开始新对局")
        new_session_button.clicked.connect(self.start_new_session)
        rematch_button = QPushButton("按勾选结果匹配路线")
        rematch_button.clicked.connect(self.match_routes_from_checked_results)
        select_route_button = QPushButton("选择当前路线")
        select_route_button.clicked.connect(self.select_current_route)
        self.session_info_label = QLabel("展开路线：随卡组包载入")
        self.phase_combo = QComboBox()
        self.phase_combo.addItem("主要阶段 1", Phase.MAIN1)
        self.phase_combo.addItem("主要阶段 2", Phase.MAIN2)
        self.phase_combo.addItem("阶段未知", Phase.UNKNOWN)
        self.normal_summon_combo = QComboBox()
        self.normal_summon_combo.addItem("通召可用", UsageState.AVAILABLE)
        self.normal_summon_combo.addItem("通召已用", UsageState.USED)
        self.normal_summon_combo.addItem("通召未知", UsageState.UNKNOWN)
        session_toolbar.addWidget(new_session_button)
        session_toolbar.addWidget(rematch_button)
        session_toolbar.addWidget(select_route_button)
        session_toolbar.addWidget(self.phase_combo)
        session_toolbar.addWidget(self.normal_summon_combo)
        session_toolbar.addWidget(self.session_info_label, 1)
        root_layout.addLayout(session_toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        self.preview_label = QLabel("请截取游戏窗口或打开本地截图")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(820, 520)
        self.preview_label.setStyleSheet(
            "QLabel { background: #15171a; color: #d4d7dc; border: 1px solid #343940; }"
        )
        preview_layout.addWidget(self.preview_label)
        self.capture_info_label = QLabel("尚未加载画面")
        preview_layout.addWidget(self.capture_info_label)
        splitter.addWidget(preview_container)

        calibration_panel = QWidget()
        calibration_layout = QVBoxLayout(calibration_panel)

        profile_label = QLabel(
            f"配置：{self.profile.profile_id}\n"
            f"参考尺寸：{self.profile.reference_width}×{self.profile.reference_height}"
        )
        calibration_layout.addWidget(profile_label)

        self.region_list = QListWidget()
        self.region_list.currentItemChanged.connect(self._on_region_selected)
        calibration_layout.addWidget(self.region_list, 1)

        analysis_group = QGroupBox("识别结果（取消勾选可排除误判）")
        analysis_layout = QVBoxLayout(analysis_group)
        self.analysis_list = QListWidget()
        self.analysis_list.setMinimumHeight(150)
        self.analysis_list.itemChanged.connect(lambda _item: self._render_preview())
        analysis_layout.addWidget(self.analysis_list)
        calibration_layout.addWidget(analysis_group)

        route_group = QGroupBox("可用展开路线")
        route_layout = QVBoxLayout(route_group)
        self.route_list = QListWidget()
        self.route_list.setMinimumHeight(170)
        self.route_list.itemDoubleClicked.connect(self.show_route_details)
        route_layout.addWidget(self.route_list)
        calibration_layout.addWidget(route_group)

        editor_group = QGroupBox("选中 ROI（归一化坐标）")
        editor_form = QFormLayout(editor_group)
        self.x_spin = self._create_roi_spin()
        self.y_spin = self._create_roi_spin()
        self.width_spin = self._create_roi_spin()
        self.height_spin = self._create_roi_spin()
        editor_form.addRow("X", self.x_spin)
        editor_form.addRow("Y", self.y_spin)
        editor_form.addRow("宽", self.width_spin)
        editor_form.addRow("高", self.height_spin)
        calibration_layout.addWidget(editor_group)

        apply_button = QPushButton("应用到预览")
        apply_button.clicked.connect(self.apply_region_changes)
        save_profile_button = QPushButton("保存 ROI 配置")
        save_profile_button.clicked.connect(self.save_profile)
        calibration_layout.addWidget(apply_button)
        calibration_layout.addWidget(save_profile_button)

        help_label = QLabel(
            "提示：默认坐标只是初始估计。\n"
            "先选择一个 ROI，再调整 X/Y/宽/高。\n"
            "保存前会检查区域是否越界。"
        )
        help_label.setWordWrap(True)
        calibration_layout.addWidget(help_label)

        splitter.addWidget(calibration_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(central)

    @staticmethod
    def _create_roi_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.0025)
        return spin

    def _populate_regions(self) -> None:
        self.region_list.clear()
        for region in self.profile.regions:
            item = QListWidgetItem(f"{region.label}  [{region.name}]")
            item.setData(Qt.ItemDataRole.UserRole, region.name)
            self.region_list.addItem(item)
        if self.region_list.count():
            self.region_list.setCurrentRow(0)

    def refresh_windows(self) -> None:
        self.window_items = list_visible_windows(only_master_duel=True)
        self.window_combo.clear()
        for window in self.window_items:
            self.window_combo.addItem(window.display_name)

        if not self.window_items:
            self.window_combo.addItem("未找到 Master Duel 窗口，可打开本地截图")
            self.statusBar().showMessage("未找到 Master Duel 窗口")
        else:
            self.statusBar().showMessage(f"找到 {len(self.window_items)} 个候选窗口")

    def capture_selected_window(self) -> None:
        index = self.window_combo.currentIndex()
        if not self.window_items or index < 0 or index >= len(self.window_items):
            QMessageBox.information(
                self,
                "未找到游戏窗口",
                "请先启动 Master Duel 并点击“刷新窗口”，或使用“打开本地截图”。",
            )
            return

        window = self.window_items[index]
        self.statusBar().showMessage("正在截取稳定画面...")
        try:
            stable = self.stable_selector.capture(self.capture_provider, window)
        except Exception as exc:  # pragma: no cover - depends on desktop state
            QMessageBox.critical(self, "截图失败", str(exc))
            return

        self.raw_frame = stable.frame
        stability_text = "稳定" if stable.is_stable else "仍有画面变化"
        self.capture_info_label.setText(
            f"{window.title} | {stable.frame.shape[1]}×{stable.frame.shape[0]} | "
            f"{stability_text} | 变化分数 {stable.motion_score:.2f}"
        )
        self._render_preview()
        self.statusBar().showMessage("截图完成")

    def open_local_image(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "打开 Master Duel 截图",
            str(self.project_root),
            "图片 (*.png *.jpg *.jpeg *.bmp)",
        )
        if not filename:
            return

        frame = cv2.imdecode(np.fromfile(filename, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            QMessageBox.warning(self, "读取失败", "无法读取所选图片。")
            return

        self.raw_frame = frame
        self.capture_info_label.setText(
            f"本地截图：{Path(filename).name} | {frame.shape[1]}×{frame.shape[0]}"
        )
        self._render_preview()

    def _on_region_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        region = self.profile.get_region(current.data(Qt.ItemDataRole.UserRole))
        self.x_spin.setValue(region.x)
        self.y_spin.setValue(region.y)
        self.width_spin.setValue(region.width)
        self.height_spin.setValue(region.height)
        self._render_preview()

    def apply_region_changes(self) -> None:
        region = self._selected_region()
        if region is None:
            return

        previous = (region.x, region.y, region.width, region.height)
        region.x = self.x_spin.value()
        region.y = self.y_spin.value()
        region.width = self.width_spin.value()
        region.height = self.height_spin.value()
        try:
            region.validate()
        except ValueError as exc:
            region.x, region.y, region.width, region.height = previous
            QMessageBox.warning(self, "ROI 无效", str(exc))
            return
        self._render_preview()

    def save_profile(self) -> None:
        try:
            self.profile.save(self.profile_path)
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        self.statusBar().showMessage(f"已保存：{self.profile_path}")

    def save_debug_images(self) -> None:
        if self.raw_frame is None:
            QMessageBox.information(self, "没有画面", "请先截图或打开本地图片。")
            return

        self.capture_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        raw_path = self.capture_dir / f"{timestamp}-raw.png"
        overlay_path = self.capture_dir / f"{timestamp}-roi.png"
        self._write_image(raw_path, self.raw_frame)
        overlay = self.preview_frame if self.preview_frame is not None else self.raw_frame
        self._write_image(overlay_path, overlay)
        self.statusBar().showMessage(f"已保存：{raw_path.name}、{overlay_path.name}")

    def import_deck_pack(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "导入卡组包",
            str(self.project_root / "deck-packs"),
            "YGO Combo Deck Pack (*.ygopack)",
        )
        if not filename:
            return

        try:
            pack = load_deck_pack(Path(filename))
            deck = pack.deck
            graph = pack.graph
            self.statusBar().showMessage(
                f"正在导入卡组包：{pack.manifest.name}……"
            )
            QApplication.processEvents()
            records = self.card_name_localizer.localize(
                self.catalog.get_many(deck.all_card_ids())
            )
            paths = self.artwork_repository.ensure_images(
                records,
                progress=self._on_artwork_progress,
            )
            feature_index = FeatureIndex.build(
                {record.card_id: path for record, path in zip(records, paths, strict=True)}
            )
            cache_name = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in (
                    f"{pack.manifest.deck_pack_id}-{pack.manifest.version}"
                )
            )
            deck_path = self.deck_dir / f"{cache_name}.json"
            feature_path = self.deck_dir / f"{cache_name}.features.npz"
            deck.save(deck_path)
            feature_index.save(feature_path)
            session_manager = SessionManager(graph)
            session = session_manager.start_new()
        except Exception as exc:
            QMessageBox.critical(self, "卡组包导入失败", str(exc))
            return

        self.current_deck_pack = pack
        self.current_deck = deck
        self.current_feature_index = feature_index
        self.current_card_records = {record.card_id: record for record in records}
        self.current_graph = graph
        self.session_manager = session_manager
        self.snapshot_analysis = None
        self.analysis_list.clear()
        self.route_list.clear()
        self.deck_info_label.setText(
            f"当前卡组包：{pack.manifest.name} {pack.manifest.version} | "
            f"主卡组 {len(deck.main)} | 额外卡组 {len(deck.extra)} | "
            f"验证状态 {pack.manifest.verification_status}"
        )
        self.session_info_label.setText(
            f"展开图：{graph.deck_pack_id} | {graph.ruleset} | "
            f"新对局 {session.session_id[:8]}"
        )
        self.statusBar().showMessage(
            "卡组包导入完成：构筑、卡图特征和展开路线已全部载入"
        )

    def _on_artwork_progress(
        self,
        index: int,
        total: int,
        record: CardRecord,
    ) -> None:
        self.statusBar().showMessage(
            f"准备卡图 {index}/{total}：{record.display_name}"
        )
        QApplication.processEvents()

    def analyze_current_snapshot(self) -> None:
        if self.raw_frame is None:
            QMessageBox.information(self, "没有画面", "请先截取游戏画面或打开本地截图。")
            return
        if self.current_deck is None or self.current_feature_index is None:
            QMessageBox.information(self, "没有卡组包", "请先导入卡组包。")
            return

        self.statusBar().showMessage("正在扫描手牌与我方场区……")
        QApplication.processEvents()
        analyzer = SnapshotAnalyzer(
            self.profile,
            self.current_deck,
            self.current_feature_index,
            self.current_card_records,
        )
        try:
            self.snapshot_analysis = analyzer.analyze(self.raw_frame)
        except Exception as exc:
            QMessageBox.critical(self, "分析失败", str(exc))
            return

        self.analysis_list.blockSignals(True)
        self.analysis_list.clear()
        for region_analysis in self.snapshot_analysis.regions:
            for match in region_analysis.matches:
                record = self.current_card_records.get(match.card_id)
                name = record.display_name if record else str(match.card_id)
                item = QListWidgetItem(
                    f"{region_analysis.region_name} | {name} | "
                    f"{match.score:.0%} | 特征点 {match.good_matches}"
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    (region_analysis.region_name, match),
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.analysis_list.addItem(item)
        self.analysis_list.blockSignals(False)
        self._render_preview()
        match_count = len(self.snapshot_analysis.matches)
        self.statusBar().showMessage(f"截图分析完成，共找到 {match_count} 个候选卡片实例")
        if self.session_manager is not None:
            self.match_routes_from_checked_results()

    def start_new_session(self) -> None:
        if self.session_manager is None:
            QMessageBox.information(self, "没有卡组包", "请先导入卡组包。")
            return
        session = self.session_manager.start_new()
        self.route_list.clear()
        self.session_info_label.setText(
            f"展开图：{self.current_graph.deck_pack_id} | 新对局 {session.session_id[:8]}"
        )
        self.statusBar().showMessage("已清空历史状态并开始新对局")

    def match_routes_from_checked_results(self) -> None:
        if self.session_manager is None:
            QMessageBox.information(self, "没有卡组包", "请先导入卡组包。")
            return
        entries = self._checked_analysis_entries()
        if self.raw_frame is None or self.snapshot_analysis is None:
            QMessageBox.information(self, "没有识别结果", "请先分析当前截图。")
            return

        hand = Counter(
            match.card_id for region_name, match in entries if region_name == "self_hand"
        )
        field = Counter(
            match.card_id for region_name, match in entries if region_name != "self_hand"
        )
        confidence = (
            sum(match.score for _region_name, match in entries) / len(entries)
            if entries
            else 0.6
        )
        observation = BoardObservation(
            hand=hand,
            field=field,
            phase=self.phase_combo.currentData(),
            normal_summon=self.normal_summon_combo.currentData(),
            confidence=max(0.0, min(1.0, confidence)),
        )
        result = self.session_manager.analyze(observation)
        self._show_analysis_result(result)

    def _show_analysis_result(self, result: AnalysisResult) -> None:
        self.route_list.clear()
        for index, route in enumerate(result.routes, start=1):
            next_step = route.next_action.instruction if route.next_action else "已到达终场"
            item = QListWidgetItem(
                f"{index}. {route.result.summary or route.terminal_node_id}\n"
                f"下一步：{next_step}\n"
                f"评分 {route.score:.1f} | 可信度 {route.confidence:.0%} | "
                f"剩余 {len(route.actions)} 步"
            )
            item.setData(Qt.ItemDataRole.UserRole, route)
            self.route_list.addItem(item)
        if result.routes:
            self.route_list.setCurrentRow(0)
        self.statusBar().showMessage(f"{result.message}；找到 {len(result.routes)} 条路线")

    def select_current_route(self) -> None:
        if self.session_manager is None:
            return
        item = self.route_list.currentItem()
        if item is None:
            QMessageBox.information(self, "没有路线", "请先选择一条可用路线。")
            return
        route = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(route, RouteCandidate):
            return
        self.session_manager.select_route(route)
        self.session_info_label.setText(
            f"已选路线：{route.result.summary or route.terminal_node_id} | "
            f"当前节点 {route.start_node_id}"
        )
        self.statusBar().showMessage("路线已选择；反制结算后再次分析即可重新规划")

    def show_route_details(self, item: QListWidgetItem) -> None:
        route = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(route, RouteCandidate):
            return
        steps = "\n".join(
            f"{index}. {action.instruction}"
            for index, action in enumerate(route.actions, start=1)
        ) or "已经处于该路线的终场节点。"
        unresolved = "、".join(route.unresolved_requirements) or "无"
        QMessageBox.information(
            self,
            "展开路线详情",
            f"预计结果：{route.result.summary}\n"
            f"剩余手牌：{route.result.remaining_hand}\n"
            f"未确认条件：{unresolved}\n\n{steps}",
        )

    @staticmethod
    def _write_image(path: Path, frame: np.ndarray) -> None:
        success, encoded = cv2.imencode(".png", frame)
        if not success:
            raise RuntimeError(f"无法编码图片：{path}")
        encoded.tofile(path)

    def _selected_region(self) -> NormalizedROI | None:
        item = self.region_list.currentItem()
        if item is None:
            return None
        return self.profile.get_region(item.data(Qt.ItemDataRole.UserRole))

    def _render_preview(self) -> None:
        if self.raw_frame is None:
            return
        selected = self._selected_region()
        selected_name = selected.name if selected is not None else None
        self.preview_frame = render_roi_overlay(
            self.raw_frame,
            self.profile,
            selected_name=selected_name,
        )
        for _region_name, match in self._checked_analysis_entries():
            polygon = np.asarray(match.polygon, dtype=np.int32)
            cv2.polylines(
                self.preview_frame,
                [polygon],
                True,
                (0, 220, 255),
                3,
                cv2.LINE_AA,
            )

        rgb = cv2.cvtColor(self.preview_frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        painter = QPainter(image)
        painter.setFont(QFont("Microsoft YaHei UI", 11))
        for _region_name, match in self._checked_analysis_entries():
            polygon = np.asarray(match.polygon, dtype=np.int32)
            record = self.current_card_records.get(match.card_id)
            name = record.display_name if record else str(match.card_id)
            anchor_x, anchor_y = polygon[0]
            label = f"{name} {match.score:.0%}"
            label_x = int(anchor_x)
            label_y = max(18, int(anchor_y) - 6)
            painter.setPen(QColor(20, 20, 20))
            painter.drawText(label_x + 1, label_y + 1, label)
            painter.setPen(QColor(255, 220, 0))
            painter.drawText(label_x, label_y, label)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _checked_analysis_entries(self) -> list[tuple[str, LocatedCardMatch]]:
        entries: list[tuple[str, LocatedCardMatch]] = []
        for index in range(self.analysis_list.count()):
            item = self.analysis_list.item(index)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if (
                isinstance(entry, tuple)
                and len(entry) == 2
                and isinstance(entry[0], str)
                and isinstance(entry[1], LocatedCardMatch)
            ):
                entries.append(entry)
        return entries

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._render_preview()

