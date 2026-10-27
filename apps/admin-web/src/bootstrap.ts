import { pinia } from './stores/pinia';
import { createApp } from 'vue';
import { create, NAlert, NAvatar, NBadge, NButton, NCard, NCheckbox, NCollapse, NCollapseItem, NCollapseTransition, NConfigProvider, NDataTable, NDatePicker, NDescriptions, NDescriptionsItem, NDialogProvider, NDivider, NDrawer, NDrawerContent, NDropdown, NEmpty, NForm, NFormItem, NGrid, NGridItem, NIcon, NInput, NInputNumber, NLayout, NLayoutContent, NLayoutFooter, NLayoutHeader, NLayoutSider, NMenu, NMessageProvider, NModal, NNumberAnimation, NPageHeader, NPagination, NPopover, NRadio, NRadioButton, NRadioGroup, NResult, NSelect, NSpace, NSpin, NStatistic, NSwitch, NTabPane, NTabs, NTag, NText, NThing, NTree } from 'naive-ui';
import App from './App.vue';
import { router } from './router';

export function bootstrap() {
  const app = createApp(App);
  const naive = create({
    components: [
      NAlert,
      NButton,
      NAvatar,
      NBadge,
      NCard,
      NCheckbox,
      NCollapse,
      NCollapseItem,
      NCollapseTransition,
      NConfigProvider,
      NDataTable,
      NDatePicker,
      NDescriptions,
      NDescriptionsItem,
      NDialogProvider,
      NDivider,
      NDrawer,
      NDrawerContent,
      NDropdown,
      NEmpty,
      NForm,
      NFormItem,
      NGrid,
      NGridItem,
      NIcon,
      NInput,
      NInputNumber,
      NLayout,
      NLayoutContent,
      NLayoutFooter,
      NLayoutHeader,
      NLayoutSider,
      NMenu,
      NMessageProvider,
      NModal,
      NNumberAnimation,
      NPageHeader,
      NPagination,
      NPopover,
      NRadio,
      NRadioButton,
      NRadioGroup,
      NResult,
      NSelect,
      NSpace,
      NSpin,
      NStatistic,
      NSwitch,
      NTabPane,
      NTabs,
      NTag,
      NText,
      NThing,
      NTree,
    ],
  });

  app.use(pinia);
  app.use(router);
  app.use(naive);
  app.mount('#app');
}
