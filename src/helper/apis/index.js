/**
 * 导出 apis 下目录的所有接口
 * 注意：快应用不支持 require.context，需手动 import
 */
import auth from './auth'
import cards from './cards'
import chat from './chat'
import chatroom from './chatroom'
import config from './config'
import family from './family'
import nvc from './nvc'
import profile_ai from './profile_ai'
import profiles from './profiles'
import replica from './replica'
import tts from './tts'

export default { auth, cards, chat, chatroom, config, family, nvc, profile_ai, profiles, replica, tts }
