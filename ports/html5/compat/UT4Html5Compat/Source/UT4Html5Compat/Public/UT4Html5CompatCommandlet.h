#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "UT4Html5CompatCommandlet.generated.h"

UCLASS()
class UT4HTML5COMPAT_API UUT4Html5CompatCommandlet : public UCommandlet
{
    GENERATED_BODY()
public:
    UUT4Html5CompatCommandlet(const FObjectInitializer& ObjectInitializer);
    virtual int32 Main(const FString& Params) override;
};
