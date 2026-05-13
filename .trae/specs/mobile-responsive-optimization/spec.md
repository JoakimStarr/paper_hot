# 移动端适配优化 Spec

## Why
当前程序在移动设备上显示效果不佳，导航栏、筛选器、论文卡片等组件在小屏幕上布局混乱，影响用户体验。需要优化移动端显示效果，同时保持电脑端样式不变。

## What Changes
- **Layout.tsx**: 优化导航栏移动端显示，添加汉堡菜单
- **Filters.tsx**: 优化筛选器在移动端的布局和交互
- **PaperCard.tsx**: 调整卡片在移动端的间距和字体大小
- **Pagination.tsx**: 优化分页组件在移动端的显示
- **page.tsx**: 调整首页布局适配移动端
- **trends/page.tsx**: 优化趋势分析页面移动端显示
- **search/page.tsx**: 优化搜索页面移动端显示
- **paper/[id]/page.tsx**: 优化论文详情页移动端显示
- **author/[name]/page.tsx**: 优化作者页面移动端显示
- **network/page.tsx**: 优化关系网络页面移动端显示
- **system/page.tsx**: 优化系统管理页面移动端显示

## Impact
- 受影响文件: frontend/src/components/Layout.tsx, Filters.tsx, PaperCard.tsx, Pagination.tsx
- 受影响页面: frontend/src/app/page.tsx, trends/page.tsx, search/page.tsx, paper/[id]/page.tsx, author/[name]/page.tsx, network/page.tsx, system/page.tsx
- 用户体验: 移动端用户可以正常浏览和使用所有功能

## ADDED Requirements
### Requirement: 移动端导航栏
The system SHALL provide a mobile-friendly navigation bar that collapses into a hamburger menu on small screens.

#### Scenario: Mobile navigation
- **WHEN** user views the site on a mobile device (screen width < 768px)
- **THEN** the navigation bar SHALL display a hamburger menu icon
- **AND** clicking the icon SHALL open a slide-out menu with navigation links
- **AND** the menu SHALL close when clicking outside or selecting a link

### Requirement: 移动端筛选器
The system SHALL adapt the filter component for mobile screens with a collapsible design.

#### Scenario: Mobile filters
- **WHEN** user views the filter section on mobile
- **THEN** filters SHALL be collapsed by default to save space
- **AND** a "筛选" button SHALL be visible to expand/collapse filters
- **AND** selected filters SHALL be displayed as chips below the button

### Requirement: 移动端论文卡片
The system SHALL optimize paper cards for mobile viewing with adjusted spacing and font sizes.

#### Scenario: Mobile paper card display
- **WHEN** user views paper cards on mobile
- **THEN** card padding SHALL be reduced (p-4 → p-3)
- **AND** title font size SHALL be adjusted (text-lg → text-base)
- **AND** author list SHALL be truncated more aggressively
- **AND** action buttons SHALL be rearranged for touch-friendly interaction

### Requirement: 移动端分页
The system SHALL provide a simplified pagination for mobile screens.

#### Scenario: Mobile pagination
- **WHEN** user views pagination on mobile
- **THEN** page numbers SHALL be limited to max 3 visible pages
- **AND** "上一页"/"下一页" buttons SHALL use icons only (no text)
- **AND** the component SHALL use a more compact layout

## MODIFIED Requirements
无

## REMOVED Requirements
无
