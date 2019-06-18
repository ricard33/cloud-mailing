(function () {
    "use strict";

    angular
        .module('app')
        .config(configure)
        .config(configureFormly)
        .run(initializeTranslations)
        .run(initMaterialDesign)
    ;

    function configure($interpolateProvider, $uibTooltipProvider) {

        $uibTooltipProvider.options({
            appendToBody: true
        });
    }

    function configureFormly(formlyConfigProvider) {

        formlyConfigProvider.setWrapper([
            // {
            //     template: [
            //         '<div class="formly-template-wrapper form-group"',
            //         'ng-class="{\'has-error\': options.validation.errorExistsAndShouldBeVisible}">',
            //         '<label for="{{::id}}">{{options.templateOptions.label}} {{options.templateOptions.required ? \'*\' : \'\'}}</label>',
            //         '<formly-transclude></formly-transclude>',
            //         '<div class="validation"',
            //         'ng-if="options.validation.errorExistsAndShouldBeVisible"',
            //         'ng-messages="options.formControl.$error">',
            //         '<div ng-messages-include="validation.html"></div>',
            //         '<div ng-message="{{::name}}" ng-repeat="(name, message) in ::options.validation.messages">',
            //         '{{message(options.formControl.$viewValue, options.formControl.$modelValue, this)}}',
            //         '</div>',
            //         '</div>',
            //         '</div>'
            //     ].join(' ')
            // },
            {
                name: 'cell-field',
                template: [
                    '<td class="cell-field">',
                    '<label for="{{::id}}">',
                    '<formly-transclude></formly-transclude>',
                    '</td>'
                ].join(' ')
            }
        ]);
    }

    function initializeTranslations(gettextCatalog) {
        gettextCatalog.setCurrentLanguage("fr");
        //gettextCatalog.debug = true;
        //gettextCatalog.loadRemote("/static/js/cm.fr.json");
    }

    function initMaterialDesign() {
        $.material.init();
    }

}());
