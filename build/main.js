"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const discord_js_1 = require("discord.js");
const voice_1 = require("@discordjs/voice");
const dotenv_1 = __importDefault(require("dotenv"));
dotenv_1.default.config();
const soundPath = node_path_1.default.join(__dirname, 'sounds');
const soundFiles = node_fs_1.default.readdirSync(soundPath).filter(file => file.endsWith('.mp3'));
let soundFilePath = {};
for (const file of soundFiles) {
    const extractExtension = file.split('.')[0];
    const filePath = node_path_1.default.join(soundPath, file);
    soundFilePath[extractExtension] = filePath;
}
const client = new discord_js_1.Client({
    intents: [
        discord_js_1.GatewayIntentBits.Guilds,
        discord_js_1.GatewayIntentBits.GuildMessages,
        discord_js_1.GatewayIntentBits.MessageContent,
        discord_js_1.GatewayIntentBits.GuildVoiceStates
    ]
});
let player = (0, voice_1.createAudioPlayer)({
    behaviors: { noSubscriber: voice_1.NoSubscriberBehavior.Pause }
});
let connection = null;
client.once(discord_js_1.Events.ClientReady, (c) => {
    var _a;
    console.log(`Ready! Logged in as ${(_a = c.user) === null || _a === void 0 ? void 0 : _a.tag}`);
});
client.on(discord_js_1.Events.MessageCreate, (message) => __awaiter(void 0, void 0, void 0, function* () {
    var _a;
    if (message.author.bot)
        return;
    const args = message.content.split(' ');
    const command = args[0];
    const soundName = args[1];
    if (command === '!play' || command === '!play2') {
        if (!soundName || !soundFilePath[soundName]) {
            yield message.reply('[ERR] Sound not found.');
            return;
        }
        const channel = (_a = message.member) === null || _a === void 0 ? void 0 : _a.voice.channel;
        if (!channel) {
            yield message.reply('[ERR] You need to be in a voice channel.');
            return;
        }
        if (!connection) {
            connection = (0, voice_1.joinVoiceChannel)({
                adapterCreator: channel.guild.voiceAdapterCreator,
                channelId: channel.id,
                guildId: channel.guild.id,
                selfDeaf: true,
                selfMute: false,
            });
            connection.subscribe(player);
        }
        const resource = (0, voice_1.createAudioResource)(soundFilePath[soundName], { inputType: voice_1.StreamType.Arbitrary });
        player.play(resource);
        yield (0, voice_1.entersState)(player, voice_1.AudioPlayerStatus.Playing, 10 * 1000);
        yield message.reply(`[INFO] Playing: ${soundName}`);
    }
    if (command === '!stop') {
        if (player) {
            player.stop();
            yield message.reply('[INFO] Stopped playback.');
        }
        if (connection) {
            connection.destroy();
            connection = null;
        }
    }
}));
client.login(process.env.TOKEN);
