<template>
    <v-container
        v-if="name"
        class="tune mx-auto"
    >
        <h1 class="my-2">
            {{ name }}
        </h1>
        <v-container
            v-if="displayableAliases.length"
            class="my-1"
        >
            <span class="font-italic text--secondary">Also known as: </span>
            <v-chip
                v-for="alias in displayableAliases"
                :key="alias"
                class="nameChip ma-1 px-2"
                label
                small
            >
                {{ alias }}
            </v-chip>
        </v-container>
        <v-container
            v-if="sourceLinks.length"
            class="my-1"
        >
            <v-chip
                v-for="link in sourceLinks"
                :key="link.url"
                :href="link.url"
                target="_blank"
                rel="noopener noreferrer"
                class="sourceChip ma-1 px-2"
                label
                small
            >
                {{ link.label }}
                <v-icon
                    right
                    x-small
                >
                    {{ icons.openInNew }}
                </v-icon>
            </v-chip>
        </v-container>
        <v-expansion-panels
            v-model="expandedIndex"
            :class="{ abcFullScreen: abcFullScreen }"
            multiple
        >
            <v-expansion-panel
                v-for="settingData in settings"
                v-show="settings"
                :key="settingData.setting_id"
                :setting="settingData"
            >
                <v-expansion-panel-header>
                    <h3 class="descriptor font-weight-medium">
                        {{
                            `${settingData.dance} in ${settingData.mode.slice(
                                0,
                                4
                            )}`
                        }}
                    </h3>
                </v-expansion-panel-header>
                <v-expansion-panel-content>
    <div class="d-flex justify-end mb-1">
        <v-btn
            small
            text
            @click="copyAbc(settingData)"
        >
            <v-icon
                left
                small
            >
                {{ copiedSettingID === settingData.setting_id ? icons.check : icons.contentCopy }}
            </v-icon>
            {{ copiedSettingID === settingData.setting_id ? 'ABC copié' : 'Copier l\'ABC' }}
        </v-btn>
    </div>
    <AbcDisplay
                    <AbcDisplay
                        :abc="settingData.abc"
                        :mode="settingData.mode"
                        :meter="settingData.meter"
                        @abcGoFullScreen="abcGoFullScreen"
                        @abcExitFullScreen="abcExitFullScreen"
                    />
                </v-expansion-panel-content>
            </v-expansion-panel>
        </v-expansion-panels>
    </v-container>
    <!-- This actually shouldn't ever happen unless the user manually navigates to /tunes -->
    <v-container v-else-if="!tuneID">
        <p class="px-10">
            No tune loaded. Please search for a tune.
        </p>
    </v-container>
</template>

<script>
import { mdiOpenInNew, mdiContentCopy, mdiCheck } from '@mdi/js';
import utils from '@/js/utils.js';
import AbcDisplay from '@/components/AbcDisplay';
import ffBackend from '@/services/backend.js';
import eventBus from '@/eventBus';
import { stopActiveSynth } from '@/services/player.js';

export default {
    name: 'TuneView',
    components: { AbcDisplay },
    props: {
        tuneID: {
            type: String,
            required: true
        },
        displayName: {
            type: String,
            required: true
        },
        settingID: {
            type: String,
            required: false,
            default: null
        },
    },
    data: function () {
        return {
            settings: null,
            name: null,
            displayableAliases: [],
            abcFullScreen: false,
            copiedSettingID: null,
            expandedIndex: [],

            icons: {
                openInNew: mdiOpenInNew,
                contentCopy: mdiContentCopy,
                check: mdiCheck,
            },
        };
    },

    computed: {
        // Liens vers la page d'origine de l'ABC (FolkWiki.se pour ce corpus).
        //  Seules les adresses http(s) sont acceptées ; les doublons sont fusionnés.
        sourceLinks: function () {
            const urls = [];
            for (const setting of this.settings || []) {
                const url = setting.source_url;
                if (url && /^https?:\/\//.test(url) && !urls.includes(url)) {
                    urls.push(url);
                }
            }
            return urls.map((url, i) => ({
                url: url,
                label: urls.length > 1 ? `Source ${i + 1}` : 'Source',
            }));
        },
    },

    created: async function () {
        eventBus.$emit('childViewActivated');

        if (typeof this.tuneID === 'undefined') {
            return;
        }

        this.settings = await ffBackend.settingsFromTuneID(this.tuneID);
        let aliases = await ffBackend.aliasesFromTuneID(this.tuneID);

        let primaryAliasIndex = 0;

        if (typeof this.displayName !== 'undefined') {
            primaryAliasIndex = aliases.indexOf(this.displayName);
            if (primaryAliasIndex == -1) {
                console.warn('Display name was not found in aliases!');
                primaryAliasIndex = 0;
            }
        }

        this.displayableAliases = aliases.map((a) =>
            utils.parseDisplayableName(a)
        );
        this.name = this.displayableAliases.splice(primaryAliasIndex, 1)[0];

        // Auto-pop open the matched setting and scroll into view
        if (this.settingID) {
            for (const [i, setting] of this.settings.entries()) {
                if (setting.setting_id === this.settingID) {
                    this.expandedIndex = [i];
                }
            }
        } else {
            // By default, open the first tune. Only pop it open
            //  here because otherwise if it's in data() the first
            //  one pops open unwanted even when we've hit another
            //  as above.
            this.expandedIndex = [0];
        }

        // Stop any tune that might be playing already
        stopActiveSynth();

    },
    methods: {
        descriptor: function (setting) {
            return utils.parseDisplayableDescription(setting);
        },
        abcGoFullScreen: function () {
            this.abcFullScreen = true;
        },
        abcExitFullScreen: function () {
            this.abcFullScreen = false;
        },
        copyAbc: async function (setting) {
            let text = setting.abc;
            // Si l'ABC n'a pas d'en-têtes (pas de ligne K:), on les ajoute
            //  pour que le texte copié soit un ABC complet et collable.
            if (!/^K:/m.test(text)) {
                text =
                    `X:1\nT:${this.name}\nM:${setting.meter}\n` +
                    `K:${setting.mode}\n${text}`;
            }
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(text);
                } else {
                    // Repli pour les contextes non sécurisés (http hors localhost)
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.setAttribute('readonly', '');
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }
                this.copiedSettingID = setting.setting_id;
                clearTimeout(this.copiedTimer);
                this.copiedTimer = setTimeout(() => {
                    this.copiedSettingID = null;
                }, 2000);
            } catch (e) {
                console.warn('Copie de l\'ABC impossible', e);
            }
        },
    },
};
</script>

<style scoped>
.descriptor::first-letter {
    text-transform: uppercase;
    display: inline-block;
}

.tune {
    max-width: 100vh;
}

.abcFullScreen {
    z-index: 8;
}

h1 {
    font-size: x-large;
}
</style>
