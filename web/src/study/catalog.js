/**
 * 自习层目录：场景只换背景，声音在专注设置里叠加。
 * 视频：/scenes/<id>/video.mp4  海报：/scenes/<id>/poster.jpg
 * 声音：/sounds/<id>.mp3
 * 缺文件时由 SceneBackdrop 走流动兜底，页面不破。
 */

export const SCENES = [
  { id: 'lakeside-fire', name: '湖畔篝火', sky: '#1a140e', glow: '#d45a18', mist: '#3a2a1c' },
  { id: 'grand-library', name: '西式殿堂图书馆', sky: '#2a1c12', glow: '#c9a56a', mist: '#4a3424' },
  { id: 'night-train', name: '夜行列车', sky: '#0c1018', glow: '#d8b56a', mist: '#1c2430' },
  { id: 'rainy-window', name: '雨落窗前', sky: '#1a242c', glow: '#7aa0b4', mist: '#2a3840' },
  { id: 'bamboo-wind', name: '竹林听风', sky: '#142018', glow: '#7dad62', mist: '#1e3022' },
  { id: 'snow-peak', name: '雪峰窗景', sky: '#d8e4ee', glow: '#ffffff', mist: '#9bb0c2' },
  { id: 'star-desk', name: '星空书桌', sky: '#0a1020', glow: '#e8c47a', mist: '#1a2440' },
  { id: 'wheat-field', name: '麦浪草原', sky: '#c9a24a', glow: '#f3d98a', mist: '#7a9a48' },
  { id: 'whale-deep', name: '深海鲸落', sky: '#041420', glow: '#3aa0c8', mist: '#0a2838' },
  { id: 'siheyuan-study', name: '四合院书房', sky: '#3a2414', glow: '#e07a3a', mist: '#5a3820' },
  { id: 'apothecary-desk', name: '药房书桌', sky: '#2a2218', glow: '#86a05a', mist: '#4a3a28' },
  { id: 'city-loft', name: '城市夜景落地窗', sky: '#101018', glow: '#6ab4e0', mist: '#282838' },
  { id: 'sunny-meadow', name: '暖阳草甸', sky: '#8ec8e8', glow: '#f4e08a', mist: '#7cba62' },
  { id: 'fishing-wind', name: '垂钓听风', sky: '#4a7088', glow: '#d8e8f0', mist: '#6a8890' },
  { id: 'quiet-valley', name: '深谷静心', sky: '#2a3830', glow: '#c8d8c0', mist: '#4a5850' },
]

export const SOUNDS = [
  { id: 'spring-rain', name: '春夜小雨' },
  { id: 'summer-frogs', name: '夏夜蛙声' },
  { id: 'fireplace', name: '壁炉' },
  { id: 'cafe', name: '咖啡馆' },
  { id: 'keyboard', name: '键盘' },
  { id: 'waves', name: '海浪' },
  { id: 'wind', name: '风' },
  { id: 'thunder', name: '雷' },
  { id: 'train', name: '火车' },
  { id: 'stream', name: '溪流' },
  { id: 'cicada', name: '虫鸣' },
  { id: 'birds', name: '鸟鸣' },
]

export function sceneVideo(id) {
  return `/scenes/${id}/video.mp4`
}

export function scenePoster(id) {
  return `/scenes/${id}/poster.jpg`
}

export function soundSrc(id) {
  return `/sounds/${id}.mp3`
}
