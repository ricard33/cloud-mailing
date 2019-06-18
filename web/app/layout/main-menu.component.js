(function () {
    'use strict';

    angular.module('app')
        .component('mainMenu', {
            templateUrl: 'layout/main-menu.html',
            controller: MenuController,
            bindings: {
                class: '@'
            }
        });

    function MenuController($scope, $log, $state, gettextCatalog, api) {
        var vm = this;
        vm.entries = [];
        vm.showMenu = true;
        vm.isActive = isActive;
        vm.isOpen = isOpen;

        initializeMenu();

        $scope.$on("cm.show_hide_menu", function (/*event*/) {
            vm.showMenu = !vm.showMenu;
        });
        
        function initializeMenu(){
            vm.entries = [
                {title: gettextCatalog.getString('Dashboard'), url: "index", icon: 'fa-dashboard'},
                {title: gettextCatalog.getString('Mailings'), url: "mailings", icon: 'fa-tasks'},
                //{title: gettextCatalog.getString("Domains stats"), url: 'domains-stats', icon: 'fa-globe'},
                //{title: gettextCatalog.getString('Supervision'), icon: 'fa-eye',  subitems: [
                //    {title: gettextCatalog.getString("by Domains"), url: 'stats-domain', icon: 'fa-globe'},
                //    //{title: gettextCatalog.getString("DNS"), url: '#/settings/dns', icon: 'fa-network'},
                //    //{title: gettextCatalog.getString("Date & Timezone"), url: 'settings-time', icon: 'fa-clock-o'},
                //    //{title: gettextCatalog.getString("CloudMailing"), url: 'settings-cm', icon: 'fa-cloud'},
                //    //{title: gettextCatalog.getString("Satellites"), url: 'settings-satellites', icon: 'fa-satellite'},
                //    //{title: gettextCatalog.getString("Authentication"), url: 'settings-auth', icon: 'fa-key'}
                //]},
                // {title: gettextCatalog.getString('Settings'), url: "settings", icon: 'fa-gears' },
                {title: gettextCatalog.getString('Settings'), url: "settings", icon: 'fa-gears', isopen: true, subitems: [
                   // {title: gettextCatalog.getString("Network"), url: 'settings-network', icon: 'fa-wifi'},
                   //{title: gettextCatalog.getString("DNS"), url: '#/settings/dns', icon: 'fa-network'},
                   // {title: gettextCatalog.getString("Date & Timezone"), url: 'settings-time', icon: 'fa-clock-o'},
                   {title: gettextCatalog.getString("CloudMailing"), url: 'settings-cm', icon: 'fa-cloud'},
                   {title: gettextCatalog.getString("Satellites"), url: 'settings-satellites', icon: 'fa-sitemap'},
                   {title: gettextCatalog.getString("Authentication"), url: 'settings-auth', icon: 'fa-key'}
                ]}
            ];
        }

        function isActive(entry){
            if (entry.url)
                return $state.current.name === entry.url;
            return false;
        }
        
        function isOpen(entry){
            if (entry.url && entry.subitems)
                return $state.current.name.lastIndexOf(entry.url, 0) === 0;
            return false;
        }

    }

}());
